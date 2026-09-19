import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .automation import BotConfig, run_ticket_monitor, verify_browser_runtime
from .telegram_client import (
    TelegramError,
    get_latest_chat_id,
    send_telegram_message,
)


ACCESS_MODES = {
    "Escolher no navegador": "manual",
    "Fla-ID": "fla_id",
    "Público geral": "public",
}
MAX_ACCOUNT_TABS = 4


class AccountTab(ttk.Frame):
    def __init__(
        self,
        app: "TicketBotApp",
        notebook: ttk.Notebook,
        number: int,
    ) -> None:
        super().__init__(notebook, style="App.TFrame", padding=16)
        self.app = app
        self.notebook = notebook
        self.number = number
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.profile_var = tk.StringVar(value=f"Conta {number}")
        self.target_var = tk.StringVar()
        self.access_var = tk.StringVar(value="Escolher no navegador")
        self.quantity_var = tk.IntVar(value=2)
        self.interval_var = tk.IntVar(value=10)
        self.status_var = tk.StringVar(value="Pronta")

        self._build_layout()
        self.profile_var.trace_add("write", self._on_profile_name_changed)
        self.after(100, self._process_ui_queue)

    def _build_layout(self) -> None:
        settings = ttk.Frame(self, style="Card.TFrame", padding=16)
        settings.pack(fill="x")
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)

        self._field_label(settings, "Nome desta conta", 0, 0)
        self._field_label(settings, "ID ou URL do evento", 0, 1)
        ttk.Entry(
            settings,
            textvariable=self.profile_var,
            style="App.TEntry",
        ).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 2))
        ttk.Entry(
            settings,
            textvariable=self.target_var,
            style="App.TEntry",
        ).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 2))

        ttk.Label(
            settings,
            text="Use um nome diferente para manter o login isolado.",
            style="Hint.TLabel",
        ).grid(row=2, column=0, sticky="w")
        ttk.Label(
            settings,
            text="Pode deixar vazio para escolher o jogo no navegador.",
            style="Hint.TLabel",
        ).grid(row=2, column=1, sticky="w", padx=(8, 0))

        self._field_label(settings, "Modo de acesso", 3, 0)
        self._field_label(settings, "Quantidade", 3, 1)
        ttk.Combobox(
            settings,
            textvariable=self.access_var,
            values=list(ACCESS_MODES),
            state="readonly",
            style="App.TCombobox",
        ).grid(row=4, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        ttk.Spinbox(
            settings,
            from_=1,
            to=2,
            textvariable=self.quantity_var,
            state="readonly",
            style="App.TSpinbox",
        ).grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))

        self._field_label(settings, "Intervalo (segundos)", 5, 0)
        ttk.Spinbox(
            settings,
            from_=10,
            to=300,
            increment=10,
            textvariable=self.interval_var,
            style="App.TSpinbox",
        ).grid(row=6, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        ttk.Label(
            settings,
            text="Mínimo permitido: 10 segundos.",
            style="Hint.TLabel",
        ).grid(row=6, column=1, sticky="w", padx=(8, 0))

        controls = ttk.Frame(self, style="App.TFrame")
        controls.pack(fill="x", pady=(12, 10))
        self.start_button = ttk.Button(
            controls,
            text="Iniciar esta conta",
            command=lambda: self.app.start_account(self),
            style="Primary.TButton",
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            controls,
            text="Parar esta conta",
            command=self.stop,
            style="Secondary.TButton",
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            controls,
            textvariable=self.status_var,
            style="Status.TLabel",
        ).pack(side="right")

        log_card = ttk.Frame(self, style="Card.TFrame", padding=10)
        log_card.pack(fill="both", expand=True)
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

    @staticmethod
    def _field_label(parent, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text, style="App.TLabel").grid(
            row=row,
            column=column,
            sticky="w",
            pady=(10 if row else 0, 0),
            padx=(8 if column else 0, 0),
        )

    def _on_profile_name_changed(self, *_args) -> None:
        name = self.profile_var.get().strip() or f"Conta {self.number}"
        self.notebook.tab(self, text=name[:24])

    def build_config(self) -> BotConfig:
        profile_name = self.profile_var.get().strip()
        return BotConfig(
            profile_name=profile_name,
            account_label=profile_name,
            target=self.target_var.get(),
            access_mode=ACCESS_MODES[self.access_var.get()],
            desired_quantity=int(self.quantity_var.get()),
            minimum_quantity=1,
            monitor_interval_seconds=int(self.interval_var.get()),
            telegram_token=self.app.telegram_token_var.get(),
            telegram_chat_id=self.app.telegram_chat_id_var.get(),
        )

    def begin(self, config: BotConfig) -> None:
        if self.is_running():
            return

        self.stop_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("Monitorando")
        self._append_log("Monitoramento iniciado para esta conta.")
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
                claim_cart=lambda sector: self.app.claim_cart(self, sector),
            )
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))
        else:
            self.ui_queue.put(("finished", success))

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def stop(self) -> None:
        if not self.is_running():
            return
        self.status_var.set("Encerrando")
        self.stop_button.configure(state="disabled")
        self.stop_event.set()
        self._append_log("Solicitação para parar enviada.")

    def stop_for_other_account(self, winner_name: str) -> None:
        if not self.is_running():
            return
        self.stop_event.set()
        self.ui_queue.put((
            "claimed_elsewhere",
            f"A conta {winner_name} assumiu a tentativa de carrinho.",
        ))

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
                elif event == "claimed_elsewhere":
                    self._append_log(str(payload))
                    self.status_var.set("Outra conta encontrou")
                elif event == "finished":
                    self._set_idle("Concluído" if payload else "Interrompido")
                elif event == "error":
                    self._append_log(f"ERRO: {payload}")
                    self._set_idle("Erro")
                    messagebox.showerror(
                        f"TicketBOT — {self.profile_var.get()}",
                        str(payload),
                    )
        except queue.Empty:
            pass

        if self.winfo_exists():
            self.after(100, self._process_ui_queue)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_idle(self, status: str) -> None:
        self.status_var.set(status)
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled", text="Parar esta conta")
        self.app.refresh_global_status()


class TicketBotApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TicketBOT — múltiplas contas")
        self.root.geometry("1040x860")
        self.root.minsize(900, 700)
        self.root.configure(bg="#101010")

        self.telegram_token_var = tk.StringVar()
        self.telegram_chat_id_var = tk.StringVar()
        self.global_status_var = tk.StringVar(value="Nenhuma conta monitorando")
        self.global_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.account_tabs: list[AccountTab] = []
        self.next_account_number = 1
        self.claim_lock = threading.Lock()
        self.claimed_tab: AccountTab | None = None
        self.closing_deadline = 0.0

        self._configure_styles()
        self._build_layout()
        self.add_account_tab()
        self.add_account_tab()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._process_global_queue)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("App.TFrame", background="#101010")
        style.configure("Card.TFrame", background="#1b1b1b")
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
            font=("Segoe UI Semibold", 10),
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
            padding=(16, 9),
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
            padding=(14, 9),
            borderwidth=0,
        )
        style.configure(
            "Accounts.TNotebook",
            background="#101010",
            borderwidth=0,
        )
        style.configure(
            "Accounts.TNotebook.Tab",
            background="#2a2a2a",
            foreground="#ffffff",
            padding=(16, 8),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accounts.TNotebook.Tab",
            background=[("selected", "#d62d20")],
        )

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, style="App.TFrame", padding=20)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="App.TFrame")
        header.pack(fill="x", pady=(0, 12))
        tk.Label(
            header,
            text="TicketBOT",
            bg="#101010",
            fg="#ffffff",
            font=("Segoe UI Black", 25),
        ).pack(side="left")
        tk.Label(
            header,
            text="Contas isoladas • um único carrinho automático por rodada",
            bg="#101010",
            fg="#b7b7b7",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(16, 0), pady=(8, 0))

        telegram = ttk.Frame(container, style="Card.TFrame", padding=14)
        telegram.pack(fill="x")
        telegram.columnconfigure(1, weight=2)
        telegram.columnconfigure(3, weight=1)
        ttk.Label(
            telegram,
            text="Telegram compartilhado",
            style="App.TLabel",
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 8))
        ttk.Label(telegram, text="Token", style="App.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 6)
        )
        ttk.Entry(
            telegram,
            textvariable=self.telegram_token_var,
            show="•",
            style="App.TEntry",
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12))
        ttk.Label(telegram, text="Chat ID", style="App.TLabel").grid(
            row=1, column=2, sticky="w", padx=(0, 6)
        )
        ttk.Entry(
            telegram,
            textvariable=self.telegram_chat_id_var,
            style="App.TEntry",
        ).grid(row=1, column=3, sticky="ew", padx=(0, 12))
        telegram_actions = ttk.Frame(telegram, style="Card.TFrame")
        telegram_actions.grid(row=1, column=4, sticky="e")
        self.chat_id_button = ttk.Button(
            telegram_actions,
            text="Buscar Chat ID",
            command=self._find_chat_id,
            style="Secondary.TButton",
        )
        self.chat_id_button.pack(side="left", padx=(0, 6))
        self.test_button = ttk.Button(
            telegram_actions,
            text="Testar",
            command=self._test_telegram,
            style="Secondary.TButton",
        )
        self.test_button.pack(side="left")

        toolbar = ttk.Frame(container, style="App.TFrame")
        toolbar.pack(fill="x", pady=(12, 10))
        ttk.Button(
            toolbar,
            text="+ Adicionar conta",
            command=self.add_account_tab,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Remover aba atual",
            command=self.remove_current_tab,
            style="Secondary.TButton",
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            toolbar,
            text="Iniciar todas",
            command=self.start_all,
            style="Primary.TButton",
        ).pack(side="left", padx=(18, 0))
        ttk.Button(
            toolbar,
            text="Parar todas",
            command=self.stop_all,
            style="Secondary.TButton",
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            toolbar,
            textvariable=self.global_status_var,
            style="Status.TLabel",
        ).pack(side="right")

        self.notebook = ttk.Notebook(
            container,
            style="Accounts.TNotebook",
        )
        self.notebook.pack(fill="both", expand=True)

        tk.Label(
            container,
            text=(
                "Perfis de navegador separados • Telegram compartilhado • "
                "login, CAPTCHA e pagamento manuais"
            ),
            bg="#101010",
            fg="#858585",
            font=("Segoe UI", 9),
        ).pack(pady=(10, 0))

    def add_account_tab(self) -> None:
        if len(self.account_tabs) >= MAX_ACCOUNT_TABS:
            messagebox.showinfo(
                "Contas",
                f"O limite desta versão é {MAX_ACCOUNT_TABS} contas.",
            )
            return

        tab = AccountTab(self, self.notebook, self.next_account_number)
        self.next_account_number += 1
        self.account_tabs.append(tab)
        self.notebook.add(tab, text=tab.profile_var.get())
        self.notebook.select(tab)

    def remove_current_tab(self) -> None:
        if len(self.account_tabs) == 1:
            messagebox.showinfo("Contas", "Mantenha pelo menos uma conta.")
            return

        selected_id = self.notebook.select()
        selected = next(
            (tab for tab in self.account_tabs if str(tab) == selected_id),
            None,
        )
        if selected is None:
            return
        if selected.is_running():
            messagebox.showerror(
                "Contas",
                "Pare esta conta antes de remover a aba.",
            )
            return

        self.account_tabs.remove(selected)
        self.notebook.forget(selected)
        selected.destroy()

    def _validate_profiles(self) -> None:
        names = [tab.profile_var.get().strip().casefold() for tab in self.account_tabs]
        if any(not name for name in names):
            raise ValueError("Todas as abas precisam de um nome de conta.")
        if len(names) != len(set(names)):
            raise ValueError("Use um nome diferente em cada aba de conta.")

    def _reset_claim_if_idle(self) -> None:
        if any(tab.is_running() for tab in self.account_tabs):
            return
        with self.claim_lock:
            self.claimed_tab = None

    def start_account(self, tab: AccountTab) -> None:
        try:
            self._validate_profiles()
            config = tab.build_config()
        except (KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Configuração inválida", str(exc))
            return

        self._reset_claim_if_idle()
        tab.begin(config)
        self.refresh_global_status()

    def start_all(self) -> None:
        try:
            self._validate_profiles()
            configs = [tab.build_config() for tab in self.account_tabs]
        except (KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Configuração inválida", str(exc))
            return

        if not any(tab.is_running() for tab in self.account_tabs):
            with self.claim_lock:
                self.claimed_tab = None

        for tab, config in zip(self.account_tabs, configs):
            tab.begin(config)
        self.refresh_global_status()

    def stop_all(self) -> None:
        for tab in self.account_tabs:
            tab.stop()
        self.refresh_global_status()

    def claim_cart(self, winner: AccountTab, sector: str) -> bool:
        with self.claim_lock:
            if self.claimed_tab is not None:
                if self.claimed_tab is not winner:
                    winner.stop_event.set()
                return self.claimed_tab is winner

            self.claimed_tab = winner
            winner_name = winner.profile_var.get().strip()
            for tab in self.account_tabs:
                if tab is not winner:
                    tab.stop_for_other_account(winner_name)

        self.global_queue.put((
            "claim",
            f"{winner_name} encontrou disponibilidade em {sector}.",
        ))
        self._notify_claim(winner_name, sector)
        return True

    def _notify_claim(self, account_name: str, sector: str) -> None:
        token = self.telegram_token_var.get().strip()
        chat_id = self.telegram_chat_id_var.get().strip()
        if not token or not chat_id:
            return
        try:
            send_telegram_message(
                token,
                chat_id,
                (
                    "TicketBOT: ingresso disponível!\n"
                    f"Conta configurada: {account_name}\n"
                    f"Setor: {sector}\n"
                    "Esta conta assumiu a tentativa de carrinho."
                ),
            )
        except TelegramError:
            self.global_queue.put((
                "telegram_error_log",
                "Não foi possível avisar a tentativa pelo Telegram.",
            ))

    def refresh_global_status(self) -> None:
        if self.claimed_tab is not None:
            account_name = self.claimed_tab.profile_var.get().strip()
            self.global_status_var.set(
                f"{account_name} assumiu a tentativa de carrinho"
            )
            return

        running = sum(tab.is_running() for tab in self.account_tabs)
        self.global_status_var.set(
            f"Monitorando {running} conta(s)" if running else "Nenhuma conta monitorando"
        )

    def _test_telegram(self) -> None:
        token = self.telegram_token_var.get().strip()
        chat_id = self.telegram_chat_id_var.get().strip()
        if not token or not chat_id:
            messagebox.showerror("Telegram", "Informe o token e o Chat ID.")
            return
        self.test_button.configure(state="disabled")

        def worker() -> None:
            try:
                send_telegram_message(
                    token,
                    chat_id,
                    "TicketBOT: Telegram compartilhado configurado.",
                )
            except TelegramError as exc:
                self.global_queue.put(("telegram_error", str(exc)))
            else:
                self.global_queue.put(("telegram_ok", None))

        threading.Thread(target=worker, daemon=True).start()

    def _find_chat_id(self) -> None:
        token = self.telegram_token_var.get().strip()
        if not token:
            messagebox.showerror("Telegram", "Informe o token do bot.")
            return
        self.chat_id_button.configure(state="disabled")

        def worker() -> None:
            try:
                chat_id = get_latest_chat_id(token)
            except TelegramError as exc:
                self.global_queue.put(("chat_id_error", str(exc)))
            else:
                self.global_queue.put(("chat_id_ok", chat_id))

        threading.Thread(target=worker, daemon=True).start()

    def _process_global_queue(self) -> None:
        try:
            while True:
                event, payload = self.global_queue.get_nowait()
                if event == "claim":
                    self.global_status_var.set(str(payload))
                elif event == "telegram_ok":
                    self.test_button.configure(state="normal")
                    messagebox.showinfo("Telegram", "Mensagem de teste enviada.")
                elif event == "telegram_error":
                    self.test_button.configure(state="normal")
                    messagebox.showerror("Telegram", str(payload))
                elif event == "telegram_error_log":
                    messagebox.showwarning("Telegram", str(payload))
                elif event == "chat_id_ok":
                    self.telegram_chat_id_var.set(str(payload))
                    self.chat_id_button.configure(state="normal")
                    messagebox.showinfo("Telegram", "Chat ID encontrado.")
                elif event == "chat_id_error":
                    self.chat_id_button.configure(state="normal")
                    messagebox.showerror("Telegram", str(payload))
        except queue.Empty:
            pass

        self.root.after(100, self._process_global_queue)

    def _on_close(self) -> None:
        if not any(tab.is_running() for tab in self.account_tabs):
            self.root.destroy()
            return
        if not messagebox.askyesno(
            "Fechar TicketBOT",
            "Há contas monitorando. Deseja encerrar todas e fechar?",
        ):
            return
        for tab in self.account_tabs:
            tab.stop_event.set()
        self.closing_deadline = time.monotonic() + 5
        self._wait_before_close()

    def _wait_before_close(self) -> None:
        if (
            not any(tab.is_running() for tab in self.account_tabs)
            or time.monotonic() >= self.closing_deadline
        ):
            self.root.destroy()
            return
        self.root.after(100, self._wait_before_close)


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(0 if verify_browser_runtime() else 1)
    root = tk.Tk()
    TicketBotApp(root)
    root.mainloop()
