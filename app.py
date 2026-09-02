import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from src.automation import (
    BotConfig,
    run_ticket_monitor,
    verify_browser_runtime,
)
from src.telegram_client import (
    TelegramError,
    get_latest_chat_id,
    send_telegram_message,
)


ACCESS_MODES = {
    "Escolher no navegador": "manual",
    "Fla-ID": "fla_id",
    "Público geral": "public",
}


class TicketBotApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TicketBOT")
        self.root.geometry("820x820")
        self.root.minsize(760, 720)
        self.root.configure(bg="#101010")

        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.closing_deadline = 0.0

        self.target_var = tk.StringVar()
        self.access_var = tk.StringVar(value="Escolher no navegador")
        self.quantity_var = tk.IntVar(value=2)
        self.interval_var = tk.IntVar(value=30)
        self.telegram_token_var = tk.StringVar()
        self.telegram_chat_id_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto para iniciar")

        self._configure_styles()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._process_ui_queue)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "App.TFrame",
            background="#101010",
        )
        style.configure(
            "Card.TFrame",
            background="#1b1b1b",
            relief="flat",
        )
        style.configure(
            "App.TLabel",
            background="#1b1b1b",
            foreground="#f5f5f5",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Hint.TLabel",
            background="#1b1b1b",
            foreground="#b6b6b6",
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background="#101010",
            foreground="#f5f5f5",
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "App.TEntry",
            fieldbackground="#2a2a2a",
            foreground="#ffffff",
            insertcolor="#ffffff",
            bordercolor="#3c3c3c",
            padding=7,
        )
        style.configure(
            "App.TCombobox",
            fieldbackground="#2a2a2a",
            background="#2a2a2a",
            foreground="#ffffff",
            arrowcolor="#ffffff",
            padding=6,
        )
        style.configure(
            "App.TSpinbox",
            fieldbackground="#2a2a2a",
            foreground="#ffffff",
            arrowcolor="#ffffff",
            padding=6,
        )
        style.configure(
            "Primary.TButton",
            background="#d62d20",
            foreground="#ffffff",
            font=("Segoe UI Semibold", 10),
            padding=(18, 10),
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#ef3b2d"), ("disabled", "#64312d")],
        )
        style.configure(
            "Secondary.TButton",
            background="#343434",
            foreground="#ffffff",
            font=("Segoe UI Semibold", 10),
            padding=(16, 10),
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#474747"), ("disabled", "#252525")],
        )

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, style="App.TFrame", padding=24)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))

        tk.Label(
            header,
            text="TicketBOT",
            bg="#101010",
            fg="#ffffff",
            font=("Segoe UI Black", 25),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=(
                "Monitore um evento, adicione uma única seleção "
                "ao carrinho e finalize manualmente."
            ),
            bg="#101010",
            fg="#b7b7b7",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 0))

        settings_card = ttk.Frame(
            container,
            style="Card.TFrame",
            padding=18,
        )
        settings_card.pack(fill="x")
        settings_card.columnconfigure(0, weight=1)
        settings_card.columnconfigure(1, weight=1)

        self._field_label(
            settings_card,
            "ID ou URL do evento",
            0,
            0,
            columnspan=2,
        )
        target_entry = ttk.Entry(
            settings_card,
            textvariable=self.target_var,
            style="App.TEntry",
        )
        target_entry.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 2),
        )
        ttk.Label(
            settings_card,
            text=(
                "Deixe vazio para escolher o jogo no navegador, ou informe "
                "o ID/URL da página de setores."
            ),
            style="Hint.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w")

        self._field_label(settings_card, "Modo de acesso", 3, 0)
        self._field_label(settings_card, "Quantidade", 3, 1)
        access_combo = ttk.Combobox(
            settings_card,
            textvariable=self.access_var,
            values=list(ACCESS_MODES),
            state="readonly",
            style="App.TCombobox",
        )
        access_combo.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=(0, 8),
            pady=(4, 0),
        )
        quantity_spin = ttk.Spinbox(
            settings_card,
            from_=1,
            to=2,
            textvariable=self.quantity_var,
            state="readonly",
            style="App.TSpinbox",
        )
        quantity_spin.grid(
            row=4,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(4, 0),
        )

        self._field_label(settings_card, "Intervalo (segundos)", 5, 0)
        interval_spin = ttk.Spinbox(
            settings_card,
            from_=30,
            to=300,
            increment=15,
            textvariable=self.interval_var,
            style="App.TSpinbox",
        )
        interval_spin.grid(
            row=6,
            column=0,
            sticky="ew",
            padx=(0, 8),
            pady=(4, 0),
        )
        ttk.Label(
            settings_card,
            text="Mínimo permitido: 30 segundos.",
            style="Hint.TLabel",
        ).grid(row=6, column=1, sticky="w", padx=(8, 0))

        telegram_card = ttk.Frame(
            container,
            style="Card.TFrame",
            padding=18,
        )
        telegram_card.pack(fill="x", pady=(14, 0))
        telegram_card.columnconfigure(0, weight=2)
        telegram_card.columnconfigure(1, weight=1)

        ttk.Label(
            telegram_card,
            text="Avisos no Telegram",
            style="App.TLabel",
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            telegram_card,
            text="O token não é salvo no projeto nem enviado ao GitHub.",
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        self._field_label(telegram_card, "Token do bot", 2, 0)
        self._field_label(telegram_card, "Chat ID", 2, 1)
        token_entry = ttk.Entry(
            telegram_card,
            textvariable=self.telegram_token_var,
            show="•",
            style="App.TEntry",
        )
        token_entry.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=(0, 8),
            pady=(4, 0),
        )
        chat_entry = ttk.Entry(
            telegram_card,
            textvariable=self.telegram_chat_id_var,
            style="App.TEntry",
        )
        chat_entry.grid(
            row=3,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(4, 0),
        )
        telegram_buttons = ttk.Frame(
            telegram_card,
            style="Card.TFrame",
        )
        telegram_buttons.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="e",
            pady=(12, 0),
        )
        self.chat_id_button = ttk.Button(
            telegram_buttons,
            text="Buscar Chat ID",
            command=self._find_chat_id,
            style="Secondary.TButton",
        )
        self.chat_id_button.pack(side="left", padx=(0, 8))
        self.test_button = ttk.Button(
            telegram_buttons,
            text="Testar Telegram",
            command=self._test_telegram,
            style="Secondary.TButton",
        )
        self.test_button.pack(side="left")

        controls = ttk.Frame(container, style="App.TFrame")
        controls.pack(fill="x", pady=(16, 12))
        self.start_button = ttk.Button(
            controls,
            text="Iniciar monitoramento",
            command=self._start_monitor,
            style="Primary.TButton",
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            controls,
            text="Parar",
            command=self._stop_monitor,
            style="Secondary.TButton",
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(10, 0))
        ttk.Label(
            controls,
            textvariable=self.status_var,
            style="Status.TLabel",
        ).pack(side="right")

        log_card = ttk.Frame(container, style="Card.TFrame", padding=12)
        log_card.pack(fill="both", expand=True)
        log_card.configure(height=150)
        log_card.pack_propagate(False)
        self.log_text = tk.Text(
            log_card,
            height=12,
            bg="#0d0d0d",
            fg="#e8e8e8",
            insertbackground="#ffffff",
            selectbackground="#8b1d15",
            relief="flat",
            font=("Cascadia Mono", 9),
            wrap="word",
            state="disabled",
            padx=10,
            pady=10,
        )
        scrollbar = ttk.Scrollbar(
            log_card,
            orient="vertical",
            command=self.log_text.yview,
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Label(
            container,
            text=(
                "Uma inclusão por execução • Máximo de 2 ingressos • "
                "Login, CAPTCHA e pagamento manuais"
            ),
            bg="#101010",
            fg="#858585",
            font=("Segoe UI", 9),
        ).pack(anchor="center", pady=(12, 0))

    @staticmethod
    def _field_label(
        parent: ttk.Frame,
        text: str,
        row: int,
        column: int,
        columnspan: int = 1,
    ) -> None:
        ttk.Label(
            parent,
            text=text,
            style="App.TLabel",
        ).grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="w",
            pady=(12 if row else 0, 0),
        )

    def _build_config(self) -> BotConfig:
        access_mode = ACCESS_MODES[self.access_var.get()]
        return BotConfig(
            target=self.target_var.get(),
            access_mode=access_mode,
            desired_quantity=int(self.quantity_var.get()),
            minimum_quantity=1,
            monitor_interval_seconds=int(self.interval_var.get()),
            telegram_token=self.telegram_token_var.get(),
            telegram_chat_id=self.telegram_chat_id_var.get(),
        )

    def _start_monitor(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        try:
            config = self._build_config()
        except (KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Configuração inválida", str(exc))
            return

        self.stop_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal", text="Parar")
        self.test_button.configure(state="disabled")
        self.chat_id_button.configure(state="disabled")
        self.status_var.set("Monitorando")
        self._append_log("Monitoramento iniciado pela interface.")
        self.worker = threading.Thread(
            target=self._monitor_worker,
            args=(config,),
            daemon=True,
        )
        self.worker.start()

    def _monitor_worker(self, config: BotConfig) -> None:
        try:
            success = run_ticket_monitor(
                config,
                self.stop_event,
                log=self._queue_log,
                hold_after_success=self.stop_event.wait,
            )
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))
        else:
            self.ui_queue.put(("finished", success))

    def _stop_monitor(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            return

        self.status_var.set("Encerrando")
        self.stop_button.configure(state="disabled")
        self.stop_event.set()
        self._append_log("Solicitação para parar enviada.")

    def _test_telegram(self) -> None:
        token = self.telegram_token_var.get().strip()
        chat_id = self.telegram_chat_id_var.get().strip()

        if not token or not chat_id:
            messagebox.showerror(
                "Telegram",
                "Informe o token e o chat ID.",
            )
            return

        self.test_button.configure(state="disabled")

        def worker() -> None:
            try:
                send_telegram_message(
                    token,
                    chat_id,
                    "TicketBOT: mensagem de teste recebida com sucesso.",
                )
            except TelegramError as exc:
                self.ui_queue.put(("telegram_error", str(exc)))
            else:
                self.ui_queue.put(("telegram_ok", None))

        threading.Thread(target=worker, daemon=True).start()

    def _find_chat_id(self) -> None:
        token = self.telegram_token_var.get().strip()

        if not token:
            messagebox.showerror(
                "Telegram",
                "Informe o token do bot.",
            )
            return

        self.chat_id_button.configure(state="disabled")

        def worker() -> None:
            try:
                chat_id = get_latest_chat_id(token)
            except TelegramError as exc:
                self.ui_queue.put(("chat_id_error", str(exc)))
            else:
                self.ui_queue.put(("chat_id_ok", chat_id))

        threading.Thread(target=worker, daemon=True).start()

    def _queue_log(self, message: str) -> None:
        self.ui_queue.put(("log", message))

        if message == "Página do carrinho aberta.":
            self.ui_queue.put(("cart_ready", None))

    def _process_ui_queue(self) -> None:
        try:
            while True:
                event, payload = self.ui_queue.get_nowait()

                if event == "log":
                    self._append_log(str(payload))
                elif event == "cart_ready":
                    self.status_var.set("Ingressos no carrinho")
                    self.stop_button.configure(
                        state="normal",
                        text="Fechar navegador",
                    )
                elif event == "finished":
                    self._set_idle(
                        "Concluído" if payload else "Interrompido"
                    )
                elif event == "error":
                    self._append_log(f"ERRO: {payload}")
                    self._set_idle("Erro")
                    messagebox.showerror("TicketBOT", str(payload))
                elif event == "telegram_ok":
                    self.test_button.configure(state="normal")
                    messagebox.showinfo(
                        "Telegram",
                        "Mensagem de teste enviada.",
                    )
                elif event == "telegram_error":
                    self.test_button.configure(state="normal")
                    messagebox.showerror("Telegram", str(payload))
                elif event == "chat_id_ok":
                    self.telegram_chat_id_var.set(str(payload))
                    self.chat_id_button.configure(state="normal")
                    messagebox.showinfo(
                        "Telegram",
                        "Chat ID encontrado e preenchido.",
                    )
                elif event == "chat_id_error":
                    self.chat_id_button.configure(state="normal")
                    messagebox.showerror("Telegram", str(payload))
        except queue.Empty:
            pass

        self.root.after(100, self._process_ui_queue)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_idle(self, status: str) -> None:
        self.status_var.set(status)
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled", text="Parar")
        self.test_button.configure(state="normal")
        self.chat_id_button.configure(state="normal")

    def _on_close(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            self.root.destroy()
            return

        if not messagebox.askyesno(
            "Fechar TicketBOT",
            "O monitoramento está ativo. Deseja encerrar e fechar?",
        ):
            return

        self.stop_event.set()
        self.closing_deadline = time.monotonic() + 5
        self._wait_for_worker_before_close()

    def _wait_for_worker_before_close(self) -> None:
        if (
            self.worker is None
            or not self.worker.is_alive()
            or time.monotonic() >= self.closing_deadline
        ):
            self.root.destroy()
            return

        self.root.after(100, self._wait_for_worker_before_close)


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(0 if verify_browser_runtime() else 1)

    root = tk.Tk()
    TicketBotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
