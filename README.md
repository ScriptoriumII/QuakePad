# QuakePad

Bloc-notes façon **Bloc-notes Windows**, affiché comme le **mode Quake de Windows Terminal** : il descend du haut de l'écran sur un raccourci clavier global et remonte quand on a fini.

Le dépôt contient deux outils indépendants :

| Dossier | Outil | Raccourci par défaut |
|---|---|---|
| `windows/` | Application Windows (Python / PySide6) | **Alt+²** (touche sous Échap) |
| `chrome-extension/` | Extension Chrome (panneau latéral) | **Alt+Q** |

Les notes **ne sont pas synchronisées** entre les deux.

---

## 📥 Installation (recommandée)
1. Ouvrez la page **[Releases](https://github.com/ScriptoriumII/QuakePad/releases/latest)** et téléchargez `QuakePad-Setup-X.Y.Z.exe`.
2. Lancez-le : **aucun droit administrateur** n'est nécessaire (installation dans votre profil, `%LOCALAPPDATA%\Programs\QuakePad`).
3. Options proposées : icône sur le Bureau, **ouvrir les `.txt`** (et `.md`, `.log`) avec QuakePad, lancement au démarrage de Windows.
4. Raccourci dans le **menu Démarrer**. Désinstallation : Paramètres Windows → Applications (vos notes, dans `AppData\Roaming\QuakePad`, sont conservées).

> ℹ️ **Fichiers .txt par défaut** : Windows interdit aux programmes de s'imposer comme application par défaut. L'installateur inscrit QuakePad dans « Ouvrir avec » et propose d'ouvrir la page *Applications par défaut* où un clic suffit.
>
> ⚠️ L'installateur n'est pas signé numériquement : Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » → **Informations complémentaires** → **Exécuter quand même**. Chaque fichier publié est accompagné de son empreinte dans `SHA256SUMS.txt`.

Une version **portable** (`QuakePad-X.Y.Z-portable.zip`, sans installation) est aussi publiée.

### 🔄 Mises à jour automatiques
QuakePad vérifie **une fois par jour** les nouvelles versions publiées sur GitHub (☰ → *Rechercher les mises à jour…* pour vérifier tout de suite ; désactivable dans Paramètres → Général). Quand une version est disponible, un bouton **⬆ Mise à jour X** apparaît dans la barre d'état :
1. l'installateur est téléchargé **uniquement depuis GitHub** (HTTPS, hôtes vérifiés) ;
2. son **empreinte SHA-256** est comparée à `SHA256SUMS.txt` — en cas de différence, rien n'est installé ;
3. l'installation se fait en silence, puis QuakePad redémarre (session conservée).

Lancé depuis les sources (`run.bat`), QuakePad signale la nouvelle version mais la mise à jour se fait par `git pull`.

### 🚀 Publier une nouvelle version (mainteneur)
1. Mettre à jour `APP_VERSION` dans `windows/quakepad/settings.py`.
2. Créer une **étiquette annotée** (son message devient les notes de version) et la pousser :
   ```bash
   git tag -a v1.7.0 -m "Nouveautés…"
   git push origin v1.7.0
   ```
3. GitHub Actions teste, construit l'installateur, calcule les empreintes et publie la Release.

## Application Windows

### Fonctionnalités
- Fenêtre sans bordure, toujours au premier plan, qui **glisse depuis le bord choisi** : haut, bas, gauche ou droite (☰ → Affichage → Position), sur l'écran où se trouve la souris.
- **Redimensionnable** en tirant ses bords ; la taille est **mémorisée pour chaque position** et retrouvée au prochain lancement.
- **Raccourci global** configurable, indépendant de la disposition clavier (AZERTY/QWERTY).
- **Se réduit quand on clique sur une autre fenêtre** (désactivable, ou bouton 📌 pour épingler).
- **Onglets** avec un bouton **« ＋ Nouvel onglet »** accolé ; **clic droit sur un onglet** : renommer (ou double-clic), dupliquer, copier le chemin, ouvrir le dossier, fermer / fermer les autres / fermer à droite ; session restaurée (même non enregistrée, images comprises).
- **Barre de mise en forme** : taille du texte (A−, liste, A+), gras, italique, souligné, barré, couleur, listes, **tableau** (et ajout/suppression de lignes/colonnes), **image**, effacer la mise en forme.
- **Photos** : bouton image, copier-coller (capture d'écran comprise) ou glisser-déposer ; redimensionnables au clic droit (25/50/75/100 %). Elles sont intégrées au document.
- **Correction automatique par IA** (icône ✦ ou Ctrl+F7) : l'IA corrige orthographe, grammaire, accords et ponctuation **sans reformuler**, en conservant gras, tailles, images et tableaux. Passages corrigés surlignés en vert, **Ctrl+Z annule tout**. Avec une sélection, seule la sélection est corrigée. Au choix : **Claude** (API Anthropic, modèle `claude-haiku-5-5` par défaut) ou une **IA compatible OpenAI** (Ollama en local, LM Studio, Mistral…).
- **Vérification mot par mot** (icône A✓ ou F7) via LanguageTool : fautes soulignées, suggestions au clic droit, F8 = faute suivante.
- **Export PDF** (A4) et impression.
- Formats : `.txt` (encodage et fins de ligne conservés), `.html` (mise en forme + images), `.md` ; ouverture et enregistrement dans **n'importe quel dossier**.
- **Raccourcis clavier personnalisables** (☰ → Paramètres → Raccourcis).
- Thèmes **Système** (suit Windows), **Clair** et **Sombre**.
- Rechercher / remplacer (casse, mot entier, regex), zoom, retour à la ligne, barre d'état, icône de notification, instance unique, lancement au démarrage de Windows.

> ℹ️ Un fichier `.txt` reste du texte brut : le collage s'y fait sans mise en forme, et si vous ajoutez des images ou du gras, QuakePad propose d'enregistrer en `.html` pour ne rien perdre.

### Correction par IA : configuration
☰ → Paramètres → **Correction** → choisissez le **Fournisseur**, cliquez sur **Obtenir une clé…**, collez la clé, puis **Tester la connexion** :

| Fournisseur | Coût | Modèle par défaut | Confidentialité |
|---|---|---|---|
| **Google Gemini** | Gratuit (quotas), sans carte | `gemini-3.8-flash` | En gratuit, Google peut exploiter les textes : notes non sensibles |
| **Mistral** | Gratuit (quotas), sans carte | `mistral-small-latest` | En gratuit, textes possiblement utilisés pour l'entraînement |
| **Claude (Anthropic)** | Payant à l'usage (Claude Platform) | `claude-haiku-5-5` | Envoyé à Anthropic |
| **Ollama** | Gratuit, local | `mistral-nemo` | Rien ne quitte le PC |
| **Autre (compatible OpenAI)** | Selon le service | — | Groq, OpenRouter, LM Studio… : saisir l'adresse **de l'API** (`…/v1`) |

**Consommation du jour** dans la barre d'état (à côté du raccourci) : « ✦ Gemini ▬ 12 % utilisé · 88 % libre », vert / orange (70 %) / rouge (90 %), clic = paramètres. Gemini ne publie pas le quota restant par API : QuakePad compte ses propres requêtes (remise à zéro à minuit, heure du Pacifique) et calcule le pourcentage à partir du **quota gratuit** saisi dans Paramètres → Correction (visible dans Google AI Studio). Pour Groq, le quota restant est lu directement dans les réponses du serveur. Une erreur 429 affiche « quota atteint ».

Chaque fournisseur garde sa propre clé et son modèle ; les clés sont **chiffrées avec votre compte Windows (DPAPI)** dans `settings.json`.

Garde-fous : un paragraphe trop réécrit (moins de 60 % de similarité) ou dont l'IA change le nombre d'images est ignoré ; si l'IA renvoie un nombre de paragraphes différent, rien n'est modifié.

### Correction LanguageTool : confidentialité
Le texte de la note est envoyé au serveur LanguageTool configuré. Par défaut, c'est le serveur public `api.languagetool.org` (gratuit, 20 requêtes/min). Pour garder les notes en interne :
```bash
docker run -d -p 8010:8010 erikvl87/languagetool
```
puis ☰ → Paramètres → Correction → `http://serveur:8010/v2/check`.

### Raccourcis par défaut (tous modifiables)
| Action | Touches |
|---|---|
| Afficher / masquer | Alt+² (global) — Échap pour masquer |
| Nouvel onglet / fermer | Ctrl+N / Ctrl+W |
| Ouvrir / enregistrer / sous / tout | Ctrl+O / Ctrl+S / Ctrl+Maj+S / Ctrl+Alt+S |
| Exporter en PDF / imprimer | Ctrl+Maj+E / Ctrl+P |
| Gras / italique / souligné / barré | Ctrl+B / Ctrl+I / Ctrl+U / Ctrl+Maj+X |
| Agrandir / réduire le texte | Ctrl+] / Ctrl+[ |
| Listes à puces / numérotée | Ctrl+Maj+L / Ctrl+Maj+O |
| Tableau / image | Ctrl+Alt+T / Ctrl+Maj+I |
| Effacer la mise en forme / coller sans mise en forme | Ctrl+Espace / Ctrl+Maj+V |
| Correction IA / LanguageTool / faute suivante | Ctrl+F7 / F7 / F8 |
| Rechercher / remplacer / suivant / précédent | Ctrl+F / Ctrl+H / F3 / Maj+F3 |
| Atteindre la ligne / date et heure / dupliquer la ligne | Ctrl+G / F5 / Ctrl+D |
| Onglet suivant / précédent / n° | Ctrl+Tab / Ctrl+Maj+Tab / Alt+1…9 |
| Zoom / barre de mise en forme / retour à la ligne | Ctrl+= Ctrl+- Ctrl+0 / Ctrl+Maj+T / Alt+Z |
| Paramètres / quitter | Ctrl+, / Ctrl+Q |

> ⚠️ **Win+²** est déjà pris par Windows Terminal (mode Quake). Si le raccourci choisi est occupé, QuakePad l'indique dans une notification : changez-le dans **☰ → Paramètres**.

### Sécurité et confidentialité
- **Clés API et session chiffrées avec DPAPI** (liées à votre compte Windows) : le contenu des notes, y compris les onglets non enregistrés et les images, n'est jamais écrit en clair dans `%APPDATA%\QuakePad`. Une ancienne session en clair est chiffrée automatiquement au premier lancement.
- **Adresses contrôlées** : seules `https://` (ou `http://` vers ce PC / le réseau local **sans clé**) sont acceptées ; une clé API n'est jamais envoyée en clair sur le réseau ; redirections refusées ; jamais de `file://`.
- **Canal d'instance unique** réservé à votre compte Windows.
- **Dépendances figées** (versions + empreintes SHA-256 vérifiées par `pip --require-hashes`), installées uniquement quand `requirements.txt` change.
- **Journal** `quakepad.log` (☰ → Ouvrir le dossier des données) : erreurs et exceptions, clés API masquées automatiquement.
- Limite connue : DPAPI protège contre la lecture du fichier par un autre compte ou sur un autre PC, pas contre un programme malveillant exécuté sous votre propre session.

### Lancer depuis les sources
```bat
cd windows
run.bat
```

### Construire l'exécutable et l'installateur
```bat
cd windows
build.bat
```
Le script vérifie le code (ruff), lance les tests (pytest), puis produit `windows\dist\QuakePad.exe` (fichier unique, sans console). Prérequis : Python 3.10+.

### Développement
```bat
cd windows
.venv\Scripts\python.exe -m pip install --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check quakepad tests
```
- Modules : `window.py` (assemblage, menus, thème) · `quake.py` (position, animation) · `tabs.py` · `files.py` · `formatting.py` · `correction.py` · `session.py` · `widgets.py` · `editor.py` · `ai.py` · `netsec.py` · `log.py` · `settings.py` · `winapi.py`.
- Mettre à jour une dépendance : modifier `requirements.in` (ou `requirements-dev.in`) puis régénérer le fichier figé avec la commande indiquée en tête de `requirements.txt` (`uv pip compile … --universal --generate-hashes`).

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
Le workflow `.github/workflows/build.yml` lance, à chaque push et pull request, l'analyse du code et les tests sous **Ubuntu et Windows** (DPAPI réel), puis — seulement s'ils réussissent — construit `QuakePad.exe` et le zip de l'extension (onglet **Actions** → artefacts). Actions épinglées par empreinte de commit, permissions en lecture seule.
