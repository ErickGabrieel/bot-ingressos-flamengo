from threading import Event

from .automation import BotConfig, run_ticket_monitor


def wait_with_browser_open() -> None:
    input(
        "Ingressos no carrinho. "
        "Pressione Enter para fechar o navegador..."
    )


def main() -> None:
    stop_event = Event()
    config = BotConfig()

    try:
        run_ticket_monitor(
            config,
            stop_event,
            hold_after_success=wait_with_browser_open,
        )
    except KeyboardInterrupt:
        stop_event.set()
        print("Execução interrompida.")


if __name__ == "__main__":
    main()
