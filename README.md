# Screenplay Editor Backend

Backend FastAPI pour Screenplay Editor - Export FDX et Text-to-Speech.

## Endpoints

### Export FDX

```
POST /export/fdx
```
Retourne un fichier .fdx (XML)

```
POST /export/fdx/json
```
Retourne le contenu FDX en JSON (pour Apps Script)

**Body:**
```json
{
  "title": "Mon Scénario",
  "elements": [
    {"type": "SCENE_HEADING", "text": "INT. CAFÉ - JOUR"},
    {"type": "ACTION", "text": "Jules entre dans le café."},
    {"type": "CHARACTER", "text": "JULES"},
    {"type": "DIALOGUE", "text": "Salut tout le monde."}
  ]
}
```

### Text-to-Speech

```
POST /tts/prepare
```
Prépare les données pour la lecture vocale côté client (Web Speech API)

**Body:**
```json
{
  "title": "Mon Scénario",
  "elements": [...],
  "characters": [
    {"name": "JULES", "gender": "male"},
    {"name": "MARIE", "gender": "female"}
  ]
}
```

**Response:**
```json
{
  "success": true,
  "elements": [
    {
      "type": "SCENE_HEADING",
      "text": "INT. CAFÉ - JOUR",
      "voice": {
        "rate": 0.9,
        "pitch": 0.8,
        "voice_type": "narrator",
        "pause_after": 1000
      }
    },
    ...
  ]
}
```

## Développement local

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur
python main.py

# Ou avec uvicorn (hot reload)
uvicorn main:app --reload --port 8080
```

API disponible sur http://localhost:8080

Documentation Swagger: http://localhost:8080/docs

## Déploiement Cloud Run

### Prérequis

1. Avoir un compte Google Cloud
2. Installer [gcloud CLI](https://cloud.google.com/sdk/docs/install)
3. Créer un projet GCP

### Déploiement

```bash
# Se connecter à Google Cloud
gcloud auth login

# Configurer le projet
gcloud config set project YOUR_PROJECT_ID

# Activer les APIs nécessaires
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com

# Déployer en une commande (build + deploy)
gcloud run deploy screenplay-api \
  --source . \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated

# Ou builder et déployer séparément:

# 1. Builder l'image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/screenplay-api

# 2. Déployer sur Cloud Run
gcloud run deploy screenplay-api \
  --image gcr.io/YOUR_PROJECT_ID/screenplay-api \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated
```

### URL de production

Après déploiement, Cloud Run te donne une URL du type:
```
https://screenplay-api-xxxxx-ew.a.run.app
```

## Intégration avec l'Add-on

Dans ton Code.gs, ajoute:

```javascript
var BACKEND_URL = 'https://screenplay-api-xxxxx-ew.a.run.app';

function exportToFDXViaBackend() {
  var elements = serializeDocument(); // Ta fonction qui extrait les éléments
  
  var response = UrlFetchApp.fetch(BACKEND_URL + '/export/fdx/json', {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({
      title: DocumentApp.getActiveDocument().getName(),
      elements: elements
    })
  });
  
  var result = JSON.parse(response.getContentText());
  
  if (result.success) {
    var blob = Utilities.newBlob(result.content, 'application/xml', result.filename);
    var file = DriveApp.createFile(blob);
    return { success: true, url: file.getUrl() };
  }
  
  return { success: false, message: result.error };
}
```

## Coûts Cloud Run

- **Gratuit** jusqu'à 2 millions de requêtes/mois
- Après: ~$0.40 par million de requêtes
- Facturation à la seconde d'exécution uniquement

Pour un add-on avec quelques centaines d'utilisateurs: **~0€/mois**

## Évolutions futures

- [ ] Intégration ElevenLabs pour TTS haute qualité
- [ ] Import Fountain → Google Docs
- [ ] Analyse IA du scénario
- [ ] Génération de rapports PDF
