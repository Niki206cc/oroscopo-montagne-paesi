# Oroscopo automatico — Montagne & Paesi

Applicazione Docker per pubblicare ogni giorno su WordPress l'oroscopo dei 12 segni. Recupera i contenuti in italiano dalla API gratuita Sigastra, crea l'articolo, aggiunge la data all'immagine predefinita e pubblica tramite WordPress REST API.

## Funzioni

- pannello web responsive;
- anteprima articolo e immagine;
- upload dell'immagine base direttamente dal pannello;
- sovrapposizione della sola data `GG/MM/AAAA`;
- regolazione di posizione, dimensione, colore e contorno della data;
- pubblicazione manuale e automatica;
- controllo anti-duplicato su WordPress;
- categoria Nazionali ed Internazionali (ID 1869) preimpostata, tag e autore configurabili;
- orario di pubblicazione modificabile direttamente dal pannello;
- stato persistente, log ed healthcheck Docker.

## Installazione in Portainer

1. Apri **Stacks** → **Add stack**.
2. Scegli **Repository** e inserisci `https://github.com/Niki206cc/oroscopo-montagne-paesi`.
3. Repository reference: `refs/heads/main`; Compose path: `docker-compose.yml`.
4. Inserisci le variabili di `.env.example` nella sezione **Environment variables** dello stack.
5. Avvia lo stack e apri `http://IP-DI-HOME-ASSISTANT:8086`.
6. Carica dal pannello l'immagine base già approvata, senza data.
7. Controlla l'anteprima e premi **Avvia automazione**.

## Password applicazione WordPress

In WordPress vai su **Utenti → Profilo → Password delle applicazioni**, assegna un nome come `Oroscopo Portainer` e copia la password generata in `WP_APP_PASSWORD`. Non inserire mai la password nel repository.

## Variabili principali

| Variabile | Esempio | Descrizione |
|---|---|---|
| `WP_URL` | `https://www.montagneepaesi.com` | Indirizzo WordPress |
| `WP_USERNAME` | `nicola` | Utente WordPress |
| `WP_APP_PASSWORD` | `xxxx ...` | Password applicazione |
| `WP_POST_STATUS` | `publish` | `publish` oppure `draft` |
| `WP_CATEGORY_IDS` | `1869` | Categoria Nazionali ed Internazionali |
| `WP_TAG_IDS` | `10,11` | ID tag separati da virgola |
| `WP_AUTHOR_ID` | `2` | ID autore opzionale |
| `PUBLISH_TIME` | `05:30` | Ora italiana di pubblicazione |
| `AUTOMATION_ENABLED` | `false` | Stato iniziale; poi gestibile dal pannello |
| `SECRET_KEY` | stringa casuale | Chiave per le sessioni del pannello |

## Immagine

La grafica non è salvata nel repository: si carica dal pannello e resta nel volume Docker `oroscopo_data`. Il sistema non aggiunge altri titoli o loghi, ma scrive unicamente la data. L'immagine finale viene caricata ogni giorno nella libreria media di WordPress e impostata come immagine in evidenza.

## API e attribuzione

Il progetto usa l'endpoint standard (teaser) `https://sigastra.com/api/v1/daily?lang=it`, senza `full=1`. In fondo all'articolo viene inserito il link do-follow visibile richiesto da Sigastra. Il progetto non usa la modalità testo completo e quindi non richiede il canonical verso Sigastra.

## Sicurezza

Il pannello va usato soltanto nella rete locale. Non esporre la porta `8086` direttamente su Internet. Le credenziali sono lette esclusivamente dalle variabili d'ambiente e `.env` è escluso da Git.

## Versione

1.2.0
