// QuakePad — service worker : ouverture / fermeture du panneau latéral.

// Clic sur l'icône de la barre d'outils => ouvre le panneau.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);
});
chrome.runtime.onStartup.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);
});

// Panneaux ouverts, par fenêtre (le panneau se signale via un port nommé).
const openPanels = new Map(); // windowId -> Port

chrome.runtime.onConnect.addListener((port) => {
  if (!port.name.startsWith("panel:")) return;
  const windowId = Number(port.name.slice(6));
  openPanels.set(windowId, port);
  port.onDisconnect.addListener(() => {
    if (openPanels.get(windowId) === port) openPanels.delete(windowId);
  });
});

// Raccourci clavier (Alt+Q par défaut) : bascule façon Quake.
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "toggle-panel") return;
  const windowId = tab ? tab.windowId : chrome.windows.WINDOW_ID_CURRENT;
  const port = openPanels.get(windowId);
  if (port) {
    port.postMessage({ type: "close" });
    return;
  }
  // Doit rester synchrone (geste utilisateur) : aucun await avant open().
  chrome.sidePanel.open({ windowId }).catch(console.error);
});
