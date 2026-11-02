"""Correction : IA automatique, LanguageTool mot par mot, indicateur de consommation."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMessageBox,
)

from .ai import apply_corrections, collect_blocks
from .ai import resolve as resolve_ai
from .editor import Document
from .settings import APP_NAME
from .spell import document_text


class CorrectionMixin:
    """Méthodes de QuakeWindow liées à : correction : IA automatique, LanguageTool mot par mot, indicateur de consommation."""

    def check_spelling(self) -> None:
        doc = self.current()
        if not doc:
            return
        text = document_text(doc.document())
        if not text.strip():
            self._info("Rien à corriger.")
            return
        doc._spell_snapshot = text
        self._info("Vérification orthographe et grammaire…", keep=True)
        self.spell.check(doc, text, self.settings["spell_server"], self.settings["spell_language"])

    def _spell_done(self, doc: Document, issues: list) -> None:
        if doc not in self.docs():
            return
        if document_text(doc.document()) != getattr(doc, "_spell_snapshot", None):
            self._info("Le texte a changé pendant la vérification : relancez (F7).")
            return
        doc.set_issues(issues)
        n = len(issues)
        if n == 0:
            self._info("✓ Aucune faute trouvée.")
        else:
            sp = sum(1 for i in issues if i.kind == "spelling")
            self._info(
                f"{n} correction(s) proposée(s) : {sp} orthographe, {n - sp} grammaire/style — "
                "clic droit sur le mot souligné, F8 = suivante."
            )
            if doc is self.current():
                doc.next_issue()

    def _spell_failed(self, doc: Document, msg: str) -> None:
        self._info("Correction indisponible.")
        QMessageBox.warning(
            self,
            APP_NAME,
            f"La correction n'a pas pu être effectuée :\n{msg}\n\nServeur : {self.settings['spell_server']}",
        )

    def ai_correct(self) -> None:
        doc = self.current()
        if not doc or self._ai_busy:
            return
        cfg = self.settings
        ep = resolve_ai(cfg)
        if not ep["key"] and ep["id"] not in ("ollama", "openai"):
            QMessageBox.information(
                self,
                APP_NAME,
                "Configurez d'abord l'IA : choisissez un fournisseur "
                "(Google Gemini et Mistral sont gratuits) et collez votre clé API.",
            )
            self.open_settings(tab=3)
            return
        selection = doc.textCursor().hasSelection()
        blocks = collect_blocks(doc, selection_only=selection)
        if not blocks:
            self._info("Rien à corriger.")
            return
        self._ai_busy = True
        doc.setReadOnly(True)  # évite tout décalage pendant la requête
        for aid in ("spell.ai",):
            self._actions[aid][0].setEnabled(False)
        what = "la sélection" if selection else "la note"
        model = ep["model"]
        self._info(f"✦ Correction de {what} par IA ({model})…", keep=True)
        self._ai_cfg = dict(cfg)
        self.ai.correct(doc, blocks, self._ai_cfg)

    def _ai_finish(self, doc: Document) -> None:
        self.update_usage()
        self._ai_busy = False
        self._actions["spell.ai"][0].setEnabled(True)
        if doc in self.docs():
            doc.setReadOnly(False)

    def _ai_done(self, doc: Document, blocks: list, corrected: list) -> None:
        self._ai_finish(doc)
        if doc not in self.docs():
            return
        doc._applying_ai = True
        try:
            paras, edits, spans = apply_corrections(doc, blocks, corrected)
        finally:
            doc._applying_ai = False
        doc.issues = []  # les soulignements LanguageTool ne correspondent plus
        used = getattr(self, "_ai_cfg", {}).get("_model_used")
        via = f" (via {used}, modèle habituel surchargé)" if used and used != resolve_ai(self.settings)["model"] else ""
        if edits:
            doc.flash_ranges(spans)
            self._info(
                f"✦ {edits} correction(s) dans {paras} paragraphe(s){via} — surlignées en vert, "
                "Ctrl+Z pour tout annuler."
            )
        else:
            doc._paint_issues()
            self._info("✦ Aucune faute trouvée par l'IA.")

    def _ai_failed(self, doc: Document, msg: str) -> None:
        self._ai_finish(doc)
        self._info("Correction IA impossible.")
        QMessageBox.warning(self, APP_NAME, f"La correction par IA a échoué :\n{msg}")

    def next_issue(self) -> None:
        doc = self.current()
        if doc and not doc.next_issue():
            self._info("Aucune faute en attente (F7 pour vérifier).")

    def update_usage(self) -> None:
        """Rafraîchit l'indicateur de consommation de l'IA sélectionnée."""
        from . import usage

        ep = resolve_ai(self.settings)
        pid = ep["id"]
        name = ep["meta"]["label"].split(" —")[0].replace("Autre service compatible OpenAI…", "IA")
        name = name.replace("Google ", "")
        if pid == "ollama":
            self.usage.label.setText(f"✦ {name}")
            self.usage.bar.hide()
            self.usage.pct.setText("local · illimité")
            self.usage.setToolTip("IA locale : aucun quota.")
            self.usage.setProperty("level", "ok")
        else:
            quota = int((self.settings.get("ai_quotas") or {}).get(pid, 0))
            st = usage.status(pid, quota)
            self.usage.label.setText(f"✦ {name}")
            tip = [
                f"{name} — aujourd'hui : {st['requests']} requête(s), {usage.tokens_label(st['tokens'])} jetons",
                f"Remise à zéro dans {st['reset']}" + (" (minuit, heure du Pacifique)" if pid == "gemini" else ""),
            ]
            if st["pct_used"] is None:
                self.usage.bar.hide()
                self.usage.pct.setText(f"{st['requests']} req. aujourd'hui")
                tip.append(
                    "Pour afficher un pourcentage, indiquez votre quota gratuit (requêtes/jour) "
                    "dans Paramètres → Correction."
                )
                level = "ok"
            else:
                used = st["pct_used"]
                self.usage.bar.show()
                self.usage.bar.setValue(int(used * 10))
                if st["exhausted"]:
                    self.usage.pct.setText("quota atteint")
                else:
                    self.usage.pct.setText(f"{used:.0f} % utilisé · {100 - used:.0f} % libre")
                tip.append(f"Quota : {st['limit']} requêtes/jour (source : {st['source']})")
                if st["source"] == "QuakePad":
                    tip.append("Compté par QuakePad sur ce PC : l'usage du même projet ailleurs n'est pas inclus.")
                level = "high" if used >= 90 else "mid" if used >= 70 else "ok"
            self.usage.setToolTip("\n".join(tip) + "\n\nClic : paramètres de correction")
            self.usage.setProperty("level", level)
        for w in (self.usage, self.usage.pct, self.usage.bar):
            w.style().unpolish(w)
            w.style().polish(w)
