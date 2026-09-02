import os
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Literal
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .telegram_client import TelegramError, send_telegram_message


HOME_URL = "https://ingressos.flamengo.com.br/"
OFFICIAL_HOST = "ingressos.flamengo.com.br"
FLA_ID_HOST = "flaid.flamengo.com.br"
PUBLIC_SECTOR_PATHS = ("/buy", "/buy/sector")
FLA_ID_SECTOR_PATHS = ("/member", "/member/sector")
KNOWN_SECTOR_PATHS = PUBLIC_SECTOR_PATHS + FLA_ID_SECTOR_PATHS
PREFERRED_SECTOR_REGIONS = ("NORTE", "SUL", "LESTE", "OESTE")
AccessMode = Literal["manual", "fla_id", "public"]
LogCallback = Callable[[str], None]
HoldCallback = Callable[[], None]


class MonitorStopped(RuntimeError):
    """Raised when the user asks the monitor to stop."""


@dataclass(frozen=True)
class BotConfig:
    target: str = ""
    access_mode: AccessMode = "manual"
    desired_quantity: int = 2
    minimum_quantity: int = 1
    monitor_interval_seconds: int = 30
    telegram_token: str = ""
    telegram_chat_id: str = ""

    def __post_init__(self) -> None:
        if self.access_mode not in {"manual", "fla_id", "public"}:
            raise ValueError("Modo de acesso inválido.")

        if not 1 <= self.desired_quantity <= 2:
            raise ValueError("A quantidade deve ser 1 ou 2.")

        if not 1 <= self.minimum_quantity <= self.desired_quantity:
            raise ValueError("A quantidade mínima é inválida.")

        if self.monitor_interval_seconds < 30:
            raise ValueError(
                "O intervalo de monitoramento deve ser de pelo menos "
                "30 segundos."
            )

        has_token = bool(self.telegram_token.strip())
        has_chat_id = bool(self.telegram_chat_id.strip())

        if has_token != has_chat_id:
            raise ValueError(
                "Informe o token e o chat ID do Telegram juntos."
            )

        target = self.target.strip()

        if target.isdigit() and self.access_mode == "manual":
            raise ValueError(
                "Escolha Fla-ID ou público geral ao informar um ID."
            )


def get_profile_directory() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")

    if not local_app_data:
        raise RuntimeError("Não foi possível localizar a pasta AppData.")

    return Path(local_app_data) / "TicketBOT" / "browser-profile"


def launch_browser_context(playwright, profile_directory: Path):
    if not getattr(sys, "frozen", False):
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_directory),
            headless=False,
        )

    for channel in ("msedge", "chrome"):
        try:
            return playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_directory),
                channel=channel,
                headless=False,
            )
        except Exception:
            continue

    raise RuntimeError(
        "O aplicativo precisa do Microsoft Edge ou Google Chrome instalado."
    )


def verify_browser_runtime() -> bool:
    try:
        with sync_playwright() as playwright:
            channels = (
                ("msedge", "chrome")
                if getattr(sys, "frozen", False)
                else (None,)
            )

            for channel in channels:
                try:
                    launch_options = {"headless": True}

                    if channel is not None:
                        launch_options["channel"] = channel

                    browser = playwright.chromium.launch(**launch_options)
                    page = browser.new_page()
                    page.set_content("<title>TicketBOT</title>")
                    is_valid = page.title() == "TicketBOT"
                    browser.close()
                    return is_valid
                except Exception:
                    continue
    except Exception:
        return False

    return False


def normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def get_event_id(url: str) -> str:
    query_parameters = parse_qs(urlparse(url).query)
    event_ids = [
        event_id.strip()
        for event_id in query_parameters.get("event", [])
        if event_id.strip()
    ]

    if len(event_ids) != 1:
        raise RuntimeError(
            "Não foi possível identificar o evento pela URL: "
            f"{url}"
        )

    return event_ids[0]


def get_access_mode(url: str) -> str:
    parsed_url = urlparse(url)
    path = parsed_url.path.rstrip("/")

    if (
        parsed_url.scheme == "https"
        and parsed_url.hostname == OFFICIAL_HOST
        and path in FLA_ID_SECTOR_PATHS
    ):
        return "Fla-ID"

    if (
        parsed_url.scheme == "https"
        and parsed_url.hostname == OFFICIAL_HOST
        and path in PUBLIC_SECTOR_PATHS
    ):
        return "público geral"

    raise RuntimeError(
        "A página aberta não é uma página de setores conhecida: "
        f"{url}"
    )


def is_known_sector_url(url: str) -> bool:
    try:
        get_access_mode(url)
        get_event_id(url)
    except RuntimeError:
        return False

    return True


def resolve_target_url(target: str, access_mode: AccessMode) -> str:
    target = target.strip()

    if not target:
        return HOME_URL

    if target.isdigit():
        if access_mode == "fla_id":
            return (
                "https://ingressos.flamengo.com.br/member/sector"
                f"?event={target}"
            )

        if access_mode == "public":
            return (
                "https://ingressos.flamengo.com.br/buy/sector"
                f"?event={target}&allow-blocked-member=1"
            )

        raise ValueError("Escolha um modo de acesso para o ID informado.")

    parsed_url = urlparse(target)
    path = parsed_url.path.rstrip("/")

    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != OFFICIAL_HOST
        or path not in KNOWN_SECTOR_PATHS
    ):
        raise ValueError(
            "Use um ID numérico ou uma URL de setores do site oficial."
        )

    get_event_id(target)
    return target


def is_sector_available(sector_row: Locator) -> bool:
    class_attribute = (
        sector_row.get_attribute("class") or ""
    ).casefold()
    aria_disabled = (
        sector_row.get_attribute("aria-disabled") or ""
    ).casefold()
    unavailable_markers = ("sold", "disabled", "unavailable")

    return (
        sector_row.is_enabled()
        and aria_disabled != "true"
        and not any(
            marker in class_attribute
            for marker in unavailable_markers
        )
    )


def locate_sector_rows(page: Page) -> list[Locator]:
    sector_rows = page.locator(".match_sector")

    if sector_rows.count():
        return [
            sector_rows.nth(index)
            for index in range(sector_rows.count())
        ]

    sector_names = page.locator(".match_sector-name")
    rows: list[Locator] = []

    for index in range(sector_names.count()):
        sector_name = sector_names.nth(index)
        clickable_ancestor = sector_name.locator(
            "xpath=ancestor::*["
            "@data-sector or self::a or self::button"
            "][1]"
        )

        if clickable_ancestor.count():
            rows.append(clickable_ancestor.first)

    return rows


def show_sector_availability(
    page: Page,
    log: LogCallback = print,
) -> int:
    sector_rows = locate_sector_rows(page)
    sector_count = len(sector_rows)
    available_count = 0

    if sector_count == 0:
        log("Nenhum setor foi encontrado nesta consulta.")
        return 0

    log(f"Setores encontrados: {sector_count}")

    for index in range(sector_count):
        sector_row = sector_rows[index]
        sector_name = (
            sector_row
            .locator("h4.match_sector-name")
            .inner_text()
            .strip()
        )
        sector_price = (
            sector_row
            .locator(".match_sector-price p")
            .first
            .inner_text()
            .strip()
        )
        is_available = is_sector_available(sector_row)

        if is_available:
            available_count += 1

        status = "DISPONÍVEL" if is_available else "INDISPONÍVEL"
        log(f"[{status}] {sector_name} — {sector_price}")

    return available_count


def select_preferred_sector(
    page: Page,
    log: LogCallback = print,
) -> str | None:
    sector_rows = locate_sector_rows(page)
    sector_count = len(sector_rows)

    for preferred_region in PREFERRED_SECTOR_REGIONS:
        region_found = False

        for index in range(sector_count):
            sector_row = sector_rows[index]
            sector_name = (
                sector_row
                .locator("h4.match_sector-name")
                .inner_text()
                .strip()
            )

            if not normalize_name(sector_name).startswith(
                normalize_name(preferred_region)
            ):
                continue

            region_found = True

            if not is_sector_available(sector_row):
                log(f"Setor indisponível: {sector_name}")
                continue

            log(f"Selecionando setor: {sector_name}")
            sector_row.click()
            return sector_name

        if not region_found:
            log(f"Região não encontrada: {preferred_region}")

    return None


def configure_quantity(
    page: Page,
    desired_quantity: int,
    minimum_quantity: int,
    log: LogCallback = print,
) -> int:
    quantity_input = page.locator("#ticket_quantity")
    increase_button = page.locator("button.bootstrap-touchspin-up")

    quantity_input.wait_for(state="visible", timeout=30_000)
    current_quantity = int(quantity_input.input_value())
    log(f"Quantidade inicial: {current_quantity}")

    while current_quantity < desired_quantity:
        if not increase_button.is_enabled():
            log("O botão de aumentar está desabilitado.")
            break

        next_quantity = current_quantity + 1
        log(f"Tentando selecionar {next_quantity} ingressos...")
        increase_button.click()

        try:
            expect(quantity_input).to_have_value(
                str(next_quantity),
                timeout=5_000,
            )
        except AssertionError:
            log(
                "A quantidade não aumentou. "
                "O site pode ter limitado a quantidade."
            )
            break

        current_quantity = int(quantity_input.input_value())

    if current_quantity < minimum_quantity:
        raise RuntimeError(
            "Não foi possível selecionar a quantidade mínima."
        )

    if current_quantity < desired_quantity:
        log(
            "Quantidade desejada indisponível. "
            f"Continuando com {current_quantity}."
        )
    else:
        log(f"Quantidade selecionada: {current_quantity}")

    return current_quantity


def add_selection_to_cart(
    page: Page,
    log: LogCallback = print,
) -> None:
    buy_buttons = page.locator("button.btn.fc-btn").filter(
        has_text="Comprar"
    )
    visible_buy_buttons = []

    for index in range(buy_buttons.count()):
        button = buy_buttons.nth(index)

        if button.is_visible():
            visible_buy_buttons.append(button)

    if len(visible_buy_buttons) != 1:
        raise RuntimeError(
            "Não foi encontrado exatamente um botão Comprar visível."
        )

    buy_button = visible_buy_buttons[0]

    if not buy_button.is_enabled():
        raise RuntimeError("O botão Comprar está desabilitado.")

    log("Clicando em Comprar...")
    buy_button.click()
    page.wait_for_url(
        "**/shopping-cart**",
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    log("Página do carrinho aberta.")


def wait_for_sector_page(
    page: Page,
    stop_event: Event,
    log: LogCallback,
) -> str:
    last_url = ""

    while not stop_event.is_set():
        current_url = page.url

        if current_url != last_url:
            last_url = current_url
            parsed_url = urlparse(current_url)
            path = parsed_url.path.rstrip("/")

            if parsed_url.hostname == FLA_ID_HOST:
                log(
                    "Autenticação Fla-ID aberta. Conclua o login "
                    "manualmente no navegador."
                )
            elif path == "/login":
                log("Login necessário. Conclua-o manualmente no navegador.")
            elif path not in KNOWN_SECTOR_PATHS:
                log("Aguardando a escolha do evento no navegador...")

        try:
            sector_rows = locate_sector_rows(page)
            has_visible_sector = any(
                sector_row.is_visible()
                for sector_row in sector_rows
            )

            if (
                is_known_sector_url(current_url)
                and has_visible_sector
                and page.url == current_url
            ):
                log("Página de setores reconhecida.")
                return current_url
        except PlaywrightError:
            pass

        stop_event.wait(1)

    raise MonitorStopped("Monitoramento interrompido pelo usuário.")


def _notify_safely(
    config: BotConfig,
    text: str,
    log: LogCallback,
) -> None:
    if not config.telegram_token or not config.telegram_chat_id:
        return

    try:
        send_telegram_message(
            config.telegram_token,
            config.telegram_chat_id,
            text,
        )
    except TelegramError:
        log("Não foi possível enviar uma mensagem ao Telegram.")


def run_ticket_monitor(
    config: BotConfig,
    stop_event: Event,
    log: LogCallback = print,
    hold_after_success: HoldCallback | None = None,
) -> bool:
    target_url = resolve_target_url(config.target, config.access_mode)
    profile_directory = get_profile_directory()
    _notify_safely(config, "TicketBOT: monitoramento iniciado.", log)

    with sync_playwright() as playwright:
        context = launch_browser_context(playwright, profile_directory)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            try:
                page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
            except PlaywrightTimeoutError:
                log("A página demorou para carregar completamente.")

            if target_url == HOME_URL:
                log("Escolha o jogo e o modo de acesso no navegador.")
            else:
                log(f"Abrindo o evento configurado: {target_url}")

            log("Login e CAPTCHA, quando aparecerem, são manuais.")
            sector_url = wait_for_sector_page(page, stop_event, log)

            access_mode = get_access_mode(sector_url)
            event_id = get_event_id(sector_url)
            log(f"Acesso detectado: {access_mode}")
            log(f"Evento detectado: {event_id}")
            _notify_safely(
                config,
                (
                    "TicketBOT: evento detectado.\n"
                    f"Evento: {event_id}\n"
                    f"Acesso: {access_mode}"
                ),
                log,
            )

            while not stop_event.is_set():
                available_count = show_sector_availability(page, log)
                selected_section = select_preferred_sector(page, log)

                if selected_section is not None:
                    selected_location_indicator = page.get_by_text(
                        "Local selecionado:",
                        exact=True,
                    ).first
                    selected_location_indicator.wait_for(
                        state="visible",
                        timeout=30_000,
                    )
                    log(
                        "Setor selecionado com sucesso: "
                        f"{selected_section}"
                    )
                    selected_quantity = configure_quantity(
                        page,
                        config.desired_quantity,
                        config.minimum_quantity,
                        log,
                    )
                    add_selection_to_cart(page, log)
                    log("Monitoramento encerrado após uma inclusão.")
                    log("Nenhuma etapa de pagamento será executada.")
                    _notify_safely(
                        config,
                        (
                            "TicketBOT: ingressos no carrinho.\n"
                            f"Evento: {event_id}\n"
                            f"Setor: {selected_section}\n"
                            f"Quantidade: {selected_quantity}\n"
                            "Finalize manualmente no navegador."
                        ),
                        log,
                    )

                    if hold_after_success is not None:
                        hold_after_success()

                    return True

                if available_count:
                    log(
                        "Há setores disponíveis fora das regiões "
                        "permitidas."
                    )
                else:
                    log("Nenhum setor permitido está disponível agora.")

                log(
                    "Nova consulta em "
                    f"{config.monitor_interval_seconds} segundos."
                )

                if stop_event.wait(config.monitor_interval_seconds):
                    raise MonitorStopped(
                        "Monitoramento interrompido pelo usuário."
                    )

                try:
                    page.reload(
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                except PlaywrightTimeoutError:
                    log("A atualização da página demorou mais que o normal.")

                wait_for_sector_page(page, stop_event, log)

            raise MonitorStopped("Monitoramento interrompido pelo usuário.")
        except MonitorStopped:
            log("Monitoramento interrompido.")
            _notify_safely(
                config,
                "TicketBOT: monitoramento interrompido.",
                log,
            )
            return False
        except Exception:
            _notify_safely(
                config,
                "TicketBOT: ocorreu um erro no monitoramento.",
                log,
            )
            raise
        finally:
            context.close()
