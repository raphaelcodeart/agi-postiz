"""
Integrazione con il CRM Mamify ("API Mamify per il RAG") per l'Omnichannel
Responder: dati del cliente che scrive (saldi, ordini, movimenti, rete) e
catalogo (prodotti, gift card) messi a disposizione dell'AI come strumenti.

- mamify.py  : client HTTP di sola lettura, uno per chiave.
- tools.py   : chi e' il cliente (e come lo sappiamo), quali strumenti il
               modello puo' usare e come vengono eseguiti - e' qui che vive
               la regola di privacy "un cliente chiede solo di se stesso".
"""
