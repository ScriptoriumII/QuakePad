# QuakePad

Bloc-notes façon **Bloc-notes Windows**, affiché comme le **mode Quake de Windows Terminal** : il descend du haut de l'écran sur un raccourci clavier global et remonte quand on a fini.

Le dépôt contient deux outils indépendants :

| Dossier | Outil | Raccourci par défaut |
|---|---|---|
| `windows/` | Application Windows (Python / PySide6) | **Alt+²** (touche sous Échap) |
| `chrome-extension/` | Extension Chrome (panneau latéral) | **Alt+Q** |

Les notes **ne sont pas synchronisées** entre les deux.

---

## Application Windows

### Fonctionnalités
- Fenêtre sans bordure, toujours au premier plan, qui **glisse depuis le haut** de l'écran où se trouve la souris (multi-écrans).
- **Raccourci global** configurable, indépendant de la disposition clavier (AZERTY/QWERTY).
- Masquage automatique à la perte de focus (désactivable, ou bouton 📌 pour épingler).
- Hauteur ajustable en tirant le bord inférieur ; largeur, opacité et durée d'animation réglables.
- **Onglets** multiples, glisser-déposer de fichiers, ouverture en ligne de commande.
- **Session restaurée** au redémarrage, y compris les onglets non enregistrés (comme le Bloc-notes de Windows 11).
- Détection d'encodage (UTF-8, UTF-8 BOM, UTF-16, ANSI/Windows-1252) et des fins de ligne (CRLF/LF/CR), conservés à l'enregistrement et modifiables.
- Rechercher / remplacer intégré : casse, mot entier, expressions régulières (`\1` dans le remplacement), tout remplacer en un seul Ctrl+Z.
- Thèmes sombre / clair, zoom, retour à la ligne, barre d'état, impression.
- Icône dans la zone de notification, instance unique, lancement au démarrage de Windows (sans droits admin).

### Raccourcis
| Action | Touches |
|---|---|
| Afficher / masquer | Alt+² (configurable) — Échap pour masquer |
| Nouvel onglet / fermer | Ctrl+N / Ctrl+W |
| Ouvrir / enregistrer / enregistrer sous / tout | Ctrl+O / Ctrl+S / Ctrl+Maj+S / Ctrl+Alt+S |
| Rechercher / remplacer / suivant / précédent | Ctrl+F / Ctrl+H / F3 / Maj+F3 |
| Atteindre la ligne | Ctrl+G |
| Date et heure | F5 |
| Dupliquer la ligne | Ctrl+D |
| Onglet suivant / précédent / n° | Ctrl+Tab / Ctrl+Maj+Tab / Alt+1…9 |
| Zoom | Ctrl+= / Ctrl+- / Ctrl+0 |
| Retour à la ligne | Alt+Z |
| Paramètres / quitter | Ctrl+, / Ctrl+Q |

> ⚠️ **Win+²** est déjà pris par Windows Terminal (mode Quake). Si le raccourci choisi est occupé, QuakePad l'indique dans une notification : change-le dans **☰ → Paramètres**.

### Lancer depuis les sources
```bat
cd windows
run.bat
```

### Construire l'exécutable
```bat
cd windows
build.bat
```
Résultat : `windows\dist\QuakePad.exe` (fichier unique, sans console). Prérequis : Python 3.10+.

Données utilisateur : `%APPDATA%\QuakePad\settings.json` et `session.json`.

---

## Extension Chrome

### Fonctionnalités
- Bloc-notes dans le **panneau latéral** de Chrome ; **Alt+Q** l'ouvre et le referme (bascule façon Quake), ou clic sur l'icône.
- Notes à onglets, titre automatique (1re ligne) ou renommage (F2 / double-clic), réorganisation par glisser-déposer.
- **Sauvegarde automatique** (`chrome.storage.local`), synchronisée entre plusieurs fenêtres Chrome ouvertes.
- Rechercher / remplacer (casse, mot entier, regex avec `$1`), Ctrl+Z conservé.
- Import de fichiers texte (ou glisser-déposer), export de la note ou de toutes les notes en `.txt`.
- Thème système / sombre / clair, zoom, retour à la ligne, Tab pour indenter.

### Installation (mode développeur)
1. Ouvrir `chrome://extensions`
2. Activer **Mode développeur** (en haut à droite)
3. **Charger l'extension non empaquetée** → sélectionner le dossier `chrome-extension`
4. Épingler l'icône QuakePad ; changer le raccourci si besoin dans `chrome://extensions/shortcuts`

### Raccourcis (dans le panneau)
| Action | Touches |
|---|---|
| Nouvelle note / supprimer | Alt+N / Alt+W |
| Rechercher / remplacer | Ctrl+F / Ctrl+H (Entrée, Maj+Entrée, Ctrl+Entrée = tout) |
| Exporter / tout exporter / importer | Ctrl+S / Ctrl+Maj+S / Ctrl+O |
| Note n° / suivante / précédente | Alt+1…9 / Alt+PgSuiv / Alt+PgPréc |
| Date et heure / renommer | F5 / F2 |
| Zoom / retour à la ligne | Alt+= Alt+- Alt+0 / Alt+Z |

---

## Icônes
Générées par `tools/make_icons.py` (Pillow) pour les deux outils.

## Build automatique
Le workflow `.github/workflows/build.yml` construit `QuakePad.exe` et le zip de l'extension à chaque push sur `main` (onglet **Actions** → artefacts).
