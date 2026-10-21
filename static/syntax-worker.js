/* Run untrusted code tokenization outside the UI thread. */
self.Prism = {manual: true, disableWorkerMessageHandler: true};
importScripts('vendor/prism.js');
self.onmessage = ({data}) => {
  const grammar = Prism.languages[data.language];
  if (!grammar) { self.postMessage({html: null}); return; }
  self.postMessage({html: Prism.highlight(data.code, grammar, data.language)});
};
