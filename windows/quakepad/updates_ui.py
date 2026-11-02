"""Mises à jour : vérification (auto une fois par jour ou à la demande), téléchargement vérifié, installation."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon

from . import updater
from .log import log
from .settings import APP_NAME, APP_VERSION


class _Bridge(QObject):
    """Ramène les résultats des threads réseau dans le fil principal de Qt."""

    checked = Signal(object, bool)  # Release | None, manuel
    failed = Signal(str, bool)
    progress = Signal(int, int)
    downloaded = Signal(object)  # chemin de l'installateur
    download_failed = Signal(str)


class UpdatesMixin:
    """Méthodes de QuakeWindow liées aux mises à jour."""

    def init_updates(self) -> None:
        self._upd = _Bridge(self)
        self._upd.checked.connect(self._update_checked)
        self._upd.failed.connect(self._update_failed)
        self._upd.progress.connect(self._update_progress)
        self._upd.downloaded.connect(self._update_downloaded)
        self._upd.download_failed.connect(self._update_download_failed)
        self._upd_release = None
        self._upd_busy = False
        # Première vérification 10 s après le démarrage, puis contrôle toutes les 6 h (une fois par 24 h).
        self._upd_first = QTimer(self, singleShot=True, interval=10_000)
        self._upd_first.timeout.connect(self._auto_check)
        self._upd_first.start()
        self._upd_timer = QTimer(self, interval=6 * 3600 * 1000)
        self._upd_timer.timeout.connect(self._auto_check)
        self._upd_timer.start()

    # --- Vérification ----------------------------------------------------------------
    def _auto_check(self) -> None:
        s = self.settings
        if (
            s.get("auto_update", True)
            and time.time() - float(s.get("last_update_check", 0)) >= updater.CHECK_INTERVAL_S
        ):
            self.check_updates(manual=False)

    def check_updates(self, manual: bool = True) -> None:
        if self._upd_busy:
            return
        self._upd_busy = True
        if manual:
            self._info("Recherche de mises à jour…", keep=True)

        def run():
            try:
                rel = updater.latest_release()
                self._upd.checked.emit(rel, manual)
            except updater.UpdateError as exc:
                self._upd.failed.emit(str(exc), manual)
            except Exception as exc:  # noqa: BLE001
                log.exception("Vérification des mises à jour")
                self._upd.failed.emit(f"{type(exc).__name__} : {exc}", manual)

        threading.Thread(target=run, daemon=True).start()

    def _update_checked(self, rel, manual: bool) -> None:
        self._upd_busy = False
        self.settings["last_update_check"] = time.time()
        self.settings.save()
        if not updater.is_newer(rel.version):
            self.update_btn.hide()
            if manual:
                self._info(f"✓ QuakePad est à jour ({APP_VERSION}).")
            return
        self._upd_release = rel
        self.update_btn.setText(f"⬆ Mise à jour {rel.version}")
        self.update_btn.setToolTip(
            f"QuakePad {rel.version} est disponible (vous avez {APP_VERSION}). Cliquez pour installer."
        )
        self.update_btn.show()
        log.info("Nouvelle version disponible : %s", rel.version)
        if manual:
            self._info("")
            self.prompt_update()
        elif self.settings.get("skipped_version") != rel.version:
            self.tray.showMessage(
                APP_NAME,
                f"QuakePad {rel.version} est disponible. Cliquez sur « ⬆ Mise à jour » dans la barre d'état.",
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )

    def _update_failed(self, msg: str, manual: bool) -> None:
        self._upd_busy = False
        log.warning("Mises à jour : %s", msg)
        if manual:
            self._info("")
            QMessageBox.warning(self, APP_NAME, f"Impossible de vérifier les mises à jour :\n{msg}")

    # --- Installation ------------------------------------------------------------------
    def prompt_update(self) -> None:
        rel = self._upd_release
        if rel is None:
            self.check_updates(manual=True)
            return
        box = QMessageBox(self)
        box.setWindowTitle("Mise à jour de QuakePad")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"<b>QuakePad {rel.version}</b> est disponible (version actuelle : {APP_VERSION}).")
        size = f" ({rel.setup_size / 1e6:.0f} Mo)" if rel.setup_size else ""
        if updater.can_self_update():
            box.setInformativeText(
                f"L'installateur{size} sera téléchargé depuis GitHub, son empreinte SHA-256 vérifiée, "
                "puis QuakePad sera mis à jour et relancé. Vos notes sont conservées."
            )
            install = box.addButton("Installer maintenant", QMessageBox.ButtonRole.AcceptRole)
        else:
            box.setInformativeText(
                "QuakePad est lancé depuis les sources : mettez à jour avec « git pull origin main », "
                "ou installez la version Windows (QuakePad-Setup) depuis la page des versions."
            )
            install = None
        page = box.addButton("Voir les nouveautés", QMessageBox.ButtonRole.HelpRole)
        skip = box.addButton("Ignorer cette version", QMessageBox.ButtonRole.RejectRole)
        box.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
        if rel.notes:
            box.setDetailedText(rel.notes)
        box.exec()
        clicked = box.clickedButton()
        if clicked is page:
            QDesktopServices.openUrl(QUrl(rel.page_url))
        elif clicked is skip:
            self.settings["skipped_version"] = rel.version
            self.settings.save()
            self.update_btn.hide()
        elif install is not None and clicked is install:
            self._start_download(rel)

    def _start_download(self, rel) -> None:
        self.update_btn.setEnabled(False)
        self._info("Téléchargement de la mise à jour…", keep=True)

        def run():
            try:
                path = updater.download_verified(rel, progress=lambda d, t: self._upd.progress.emit(d, t))
                self._upd.downloaded.emit(path)
            except updater.UpdateError as exc:
                self._upd.download_failed.emit(str(exc))
            except Exception as exc:  # noqa: BLE001
                log.exception("Téléchargement de la mise à jour")
                self._upd.download_failed.emit(f"{type(exc).__name__} : {exc}")

        threading.Thread(target=run, daemon=True).start()

    def _update_progress(self, done: int, total: int) -> None:
        if total:
            self._info(f"Téléchargement de la mise à jour… {done * 100 // total} %", keep=True)

    def _update_downloaded(self, path) -> None:
        self._info("Mise à jour vérifiée : installation…", keep=True)
        self.save_session()
        try:
            updater.launch_installer(path)
        except OSError as exc:
            self._update_download_failed(f"Lancement de l'installateur impossible : {exc}")
            return
        self.quit_app()

    def _update_download_failed(self, msg: str) -> None:
        self.update_btn.setEnabled(True)
        self._info("")
        QMessageBox.warning(self, APP_NAME, f"La mise à jour a échoué :\n{msg}")
