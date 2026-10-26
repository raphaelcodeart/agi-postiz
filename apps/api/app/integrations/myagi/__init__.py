"""
myAGI: il gateway WhatsApp "fatto in casa" dell'installazione.

Un numero WhatsApp normale collegato via QR code, come con Maytapi, ma il
client che fa da "WhatsApp Web" gira su un nostro container (WAHA,
github.com/devlikeapro/waha, Apache-2.0, motore NOWEB senza browser) invece
che sui server di un fornitore a pagamento. Il resto della piattaforma lo vede
come un canale in piu' dell'Omnichannel Responder (`whatsapp_myagi`,
connectors/whatsapp_myagi.py): nessuna delle strade esistenti (Cloud API di
Meta, Maytapi) viene toccata.

- waha.py : client HTTP verso il container (sessioni, QR, invio).
- La pagina amministrativa "myAGI" (api/v1/myagi.py) gestisce le sessioni:
  creare un numero, mostrare il QR, vedere se e' collegato, scollegarlo.
"""
