import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


HOME_URL = "https://ingressos.flamengo.com.br/"

PREFERRED_SECTOR_REGIONS = (
    "NORTE",
    "SUL",
    "LESTE",
    "OESTE",
)

DESIRED_QUANTITY = 2
MINIMUM_QUANTITY = 1


def get_profile_directory() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")

    if not local_app_data:
        raise RuntimeError("Não foi possível localizar a pasta AppData.")

    return Path(local_app_data) / "TicketBOT" / "browser-profile"


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
    path = urlparse(url).path.rstrip("/")

    if path == "/member/sector":
        return "Fla-ID"

    if path == "/buy/sector":
        return "público geral"

    raise RuntimeError(
        "A página aberta não é uma página de setores conhecida: "
        f"{url}"
    )


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


def show_sector_availability(page: Page) -> None:
    sector_rows = page.locator("a.match_sector[data-sector]")
    sector_count = sector_rows.count()

    if sector_count == 0:
        raise RuntimeError("Nenhum setor foi encontrado na página.")

    print(f"Setores encontrados: {sector_count}")

    for index in range(sector_count):
        sector_row = sector_rows.nth(index)

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

        status = "DISPONÍVEL" if is_available else "INDISPONÍVEL"
        print(f"[{status}] {sector_name} — {sector_price}")


def select_preferred_sector(page: Page) -> str | None:
    sector_rows = page.locator("a.match_sector[data-sector]")
    sector_count = sector_rows.count()

    for preferred_region in PREFERRED_SECTOR_REGIONS:
        region_found = False

        for index in range(sector_count):
            sector_row = sector_rows.nth(index)

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
            is_available = is_sector_available(sector_row)

            if not is_available:
                print(f"Setor indisponível: {sector_name}")
                continue

            print(f"Selecionando setor: {sector_name}")
            sector_row.click()
            return sector_name

        if not region_found:
            print(f"Região não encontrada: {preferred_region}")

    return None

def configure_quantity(page: Page) -> int:
    quantity_input = page.locator("#ticket_quantity")
    increase_button = page.locator(
        "button.bootstrap-touchspin-up"
    )

    quantity_input.wait_for(
        state="visible",
        timeout=30_000,
    )

    current_quantity = int(quantity_input.input_value())

    print(f"Quantidade inicial: {current_quantity}")

    while current_quantity < DESIRED_QUANTITY:
        if not increase_button.is_enabled():
            print("O botão de aumentar está desabilitado.")
            break

        next_quantity = current_quantity + 1
        print(f"Tentando selecionar {next_quantity} ingressos...")

        increase_button.click()

        try:
            expect(quantity_input).to_have_value(
                str(next_quantity),
                timeout=5_000,
            )
        except AssertionError:
            print(
                "A quantidade não aumentou. "
                "O site pode ter limitado a quantidade."
            )
            break

        current_quantity = int(quantity_input.input_value())

    if current_quantity < MINIMUM_QUANTITY:
        raise RuntimeError(
            "Não foi possível selecionar a quantidade mínima."
        )

    if current_quantity < DESIRED_QUANTITY:
        print(
            f"Quantidade desejada indisponível. "
            f"Continuando com {current_quantity}."
        )
    else:
        print(f"Quantidade selecionada: {current_quantity}")

    return current_quantity
def add_selection_to_cart(page: Page) -> None:
    buy_buttons = page.locator(
        "button.btn.fc-btn"
    ).filter(
        has_text="Comprar"
    )

    visible_buy_buttons = []

    for index in range(buy_buttons.count()):
        button = buy_buttons.nth(index)

        if button.is_visible():
            visible_buy_buttons.append(button)

    if len(visible_buy_buttons) != 1:
        raise RuntimeError(
            "Não foi encontrado exatamente um botão "
            "Comprar visível."
        )

    buy_button = visible_buy_buttons[0]

    if not buy_button.is_enabled():
        raise RuntimeError("O botão Comprar está desabilitado.")

    print("Clicando em Comprar...")
    buy_button.click()

    page.wait_for_url(
        "**/shopping-cart**",
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    print("Página do carrinho aberta.")
def main() -> None:
    profile_directory = get_profile_directory()

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_directory),
            headless=False,
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(
                HOME_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
        except PlaywrightTimeoutError:
            print("A página demorou para carregar completamente.")

        print("Faça o login manualmente, se necessário.")
        print("Escolha qualquer jogo disponível e clique em 'Comprar'.")
        print(
            "Entre com Fla-ID ou clique em "
            "'Continuar como público geral'."
        )
        print("Aguardando a página de setores...")

        sector_page_indicator = page.get_by_text(
            "Selecione o setor:",
            exact=True,
        ).first

        sector_page_indicator.wait_for(
            state="visible",
            timeout=0,
        )

        access_mode = get_access_mode(page.url)
        current_event_id = get_event_id(page.url)
        print(f"Acesso detectado: {access_mode}")
        print(f"Evento detectado automaticamente: {current_event_id}")
        show_sector_availability(page)

        selected_section = select_preferred_sector(page)

        if selected_section is None:
            print("Nenhum setor preferido está disponível.")
            input("Pressione Enter para encerrar...")
            context.close()
            return

        selected_location_indicator = page.get_by_text(
            "Local selecionado:",
            exact=True,
        ).first

        selected_location_indicator.wait_for(
            state="visible",
            timeout=30_000,
        )

        print(f"Setor selecionado com sucesso: {selected_section}")

        selected_quantity = configure_quantity(page)

        print(
            f"Seleção preparada: {selected_section}, "
            f"{selected_quantity} ingresso(s)."
        )

        add_selection_to_cart(page)

        print("O bot parou na página do carrinho.")
        print("Nenhuma etapa de pagamento será executada.")

        input("Pressione Enter para encerrar este teste...")
        context.close()     


if __name__ == "__main__":
    main()
