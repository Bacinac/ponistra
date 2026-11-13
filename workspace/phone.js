// Chrome's desktop site widens the viewport, which is how a phone asks for the whole editor back.
(() => {
  const address = new URL(location.href);
  const chat = address.searchParams.get('chat') ?? '';
  // Taken off the address, or every reload would open the chat it asked for again.
  address.searchParams.delete('chat');
  history.replaceState(history.state, '', address);
  const phone = matchMedia('(pointer: coarse)').matches && Math.min(innerWidth, innerHeight) < 768;
  if (!phone && !chat) return;
  const config = document.getElementById('vscode-workbench-web-configuration');
  const settings = JSON.parse(config.getAttribute('data-settings'));
  settings.configurationDefaults = {
    ...settings.configurationDefaults,
    'ponistra.chat': chat,
    ...(phone && {
      'ponistra.phone': true,
      'workbench.activityBar.location': 'hidden',
      'workbench.statusBar.visible': false,
      'workbench.layoutControl.enabled': false,
      'window.menuBarVisibility': 'hidden',
      'window.commandCenter': false,
      'breadcrumbs.enabled': false,
    }),
  };
  config.setAttribute('data-settings', JSON.stringify(settings));
  // Without it the keyboard covers the prompt, as the page itself keeps its height.
  if (phone) document.querySelector('meta[name=viewport]').content += ', interactive-widget=resizes-content';
})();
