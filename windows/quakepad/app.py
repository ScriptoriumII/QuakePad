"""Point d'entrée : instance unique, icône, lancement de la fenêtre Quake."""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import winapi
from .settings import APP_NAME, Settings


def resource(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / "assets" / name)


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return f"{APP_NAME}-{user}"


def _send_to_running_instance(args: list[str]) -> bool:
    """Si QuakePad tourne déjà, lui transmet la commande et renvoie True."""
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(300):
        return False
    payload = "open\n" + "\n".join(args) if args else "toggle"
    sock.write(payload.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def main() -> int:
    argv = sys.argv[1:]
    hidden = "--hidden" in argv
    files = [a for a in argv if not a.startswith("--")]

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    winapi.set_app_user_model_id("ScriptoriumII.QuakePad")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    # Le style natif Windows 11 dessine lui-même le fond des menus (sombre/translucide) et ignore
    # les couleurs du thème : Fusion applique le thème QuakePad partout de façon cohérente.
    app.setStyle("Fusion")

    # Menus standards de Qt (clic droit : Copier, Coller…) en français
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    translator = QTranslator(app)
    if translator.load(QLocale("fr_FR"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    if _send_to_running_instance([str(Path(f).resolve()) for f in files]):
        return 0

    from .window import QuakeWindow  # import tardif : démarrage plus rapide pour la 2e instance

    icon = QIcon(resource("quakepad.ico"))
    if icon.isNull():
        icon = QIcon(resource("quakepad.png"))
    app.setWindowIcon(icon)

    settings = Settings.load()
    win = QuakeWindow(settings, icon)

    server = QLocalServer()
    QLocalServer.removeServer(_server_name())
    server.listen(_server_name())

    def on_connection():
        sock = server.nextPendingConnection()

        def read():
            msg = bytes(sock.readAll().data()).decode("utf-8", "replace")
            if msg.startswith("open\n"):
                win.show_animated()
                win.open_files([l for l in msg.split("\n")[1:] if l])
            else:
                win.toggle()

        sock.readyRead.connect(read)
        sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_connection)

    if files:
        win.open_files(files)
    if not hidden or files:
        win.show_animated()
    if settings.get("first_run"):
        settings["first_run"] = False
        settings.save()
        win.tray.showMessage(
            APP_NAME,
            f"QuakePad tourne dans la zone de notification.\n"
            f"Raccourci : {settings['hotkey'].get('label', '')} pour afficher / masquer.",
            QSystemTrayIcon.MessageIcon.Information, 6000,
        )
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
