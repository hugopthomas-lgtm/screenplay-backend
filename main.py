"""
Screenplay Editor Backend
FastAPI server for FDX export and Text-to-Speech
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import io
import os

app = FastAPI(
    title="Screenplay Editor API",
    description="Backend for Screenplay Editor - FDX export & TTS",
    version="1.0.0"
)

# CORS - autoriser les appels depuis Google Apps Script et l'extension Chrome
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En prod, restreindre aux domaines Google
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# MODELS
# ============================================

class ScriptElement(BaseModel):
    type: str  # SCENE_HEADING, ACTION, CHARACTER, DIALOGUE, PARENTHETICAL, TRANSITION
    text: str


class ExportFDXRequest(BaseModel):
    title: str
    elements: List[ScriptElement]


class TTSRequest(BaseModel):
    title: str
    elements: List[ScriptElement]
    voice_settings: Optional[dict] = None


class Character(BaseModel):
    name: str
    gender: Optional[str] = None  # male, female, neutral
    age: Optional[str] = None     # young, adult, old
    voice_id: Optional[str] = None


class TTSRequestAdvanced(BaseModel):
    title: str
    elements: List[ScriptElement]
    characters: Optional[List[Character]] = None


# ============================================
# FDX EXPORT
# ============================================

def escape_xml(text: str) -> str:
    """Échappe les caractères spéciaux XML"""
    if not text:
        return ""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


def generate_fdx(title: str, elements: List[ScriptElement]) -> str:
    """Génère un fichier FDX (Final Draft XML)"""
    
    # Mapping des types internes vers FDX
    type_mapping = {
        "SCENE_HEADING": "Scene Heading",
        "ACTION": "Action",
        "CHARACTER": "Character",
        "DIALOGUE": "Dialogue",
        "PARENTHETICAL": "Parenthetical",
        "TRANSITION": "Transition",
    }
    
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<FinalDraft DocumentType="Script" Template="No" Version="3">',
        '<Content>'
    ]
    
    for el in elements:
        fdx_type = type_mapping.get(el.type, "Action")
        escaped_text = escape_xml(el.text)
        xml_parts.append(f'  <Paragraph Type="{fdx_type}">')
        xml_parts.append(f'    <Text>{escaped_text}</Text>')
        xml_parts.append('  </Paragraph>')
    
    xml_parts.extend([
        '</Content>',
        '</FinalDraft>'
    ])
    
    return '\n'.join(xml_parts)


@app.post("/export/fdx")
async def export_fdx(request: ExportFDXRequest):
    """
    Exporte un scénario au format FDX (Final Draft)
    
    Retourne le fichier XML directement
    """
    try:
        fdx_content = generate_fdx(request.title, request.elements)
        
        filename = f"{request.title.replace(' ', '_')}.fdx"
        
        return Response(
            content=fdx_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export/fdx/json")
async def export_fdx_json(request: ExportFDXRequest):
    """
    Retourne le contenu FDX en JSON (pour Apps Script qui ne peut pas 
    facilement gérer les fichiers binaires)
    """
    try:
        fdx_content = generate_fdx(request.title, request.elements)
        return {
            "success": True,
            "filename": f"{request.title}.fdx",
            "content": fdx_content,
            "content_type": "application/xml"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================
# TEXT-TO-SPEECH
# ============================================

# Prénoms communs pour deviner le genre
FEMALE_NAMES = {
    "MARIE", "SOPHIE", "JULIE", "EMMA", "LÉA", "CHLOÉ", "CAMILLE", "SARAH",
    "LAURA", "CLARA", "ALICE", "ANNA", "EVA", "LISA", "MARY", "JANE", "SARAH",
    "EMMA", "OLIVIA", "AVA", "MIA", "EMILY", "ELLA", "LUCY", "GRACE"
}

MALE_NAMES = {
    "JEAN", "PIERRE", "PAUL", "JACQUES", "MICHEL", "MARC", "LUC", "THOMAS",
    "NICOLAS", "ANTOINE", "LOUIS", "HUGO", "LUCAS", "JOHN", "JAMES", "DAVID",
    "MICHAEL", "WILLIAM", "RICHARD", "ROBERT", "CHARLES", "JOSEPH"
}


def guess_gender(name: str) -> str:
    """Devine le genre d'un personnage basé sur son nom"""
    clean_name = name.upper().split()[0]  # Premier mot du nom
    
    if clean_name in FEMALE_NAMES:
        return "female"
    elif clean_name in MALE_NAMES:
        return "male"
    return "neutral"


def get_voice_for_element(
    element: ScriptElement, 
    characters: Optional[dict] = None,
    last_character: Optional[str] = None
) -> dict:
    """
    Retourne les paramètres de voix pour un élément
    
    Pour Web Speech API:
    - rate: vitesse (0.1 à 10, défaut 1)
    - pitch: hauteur (0 à 2, défaut 1)
    - voice: nom de la voix
    """
    
    # Paramètres par défaut (voix narrateur)
    voice_params = {
        "rate": 1.0,
        "pitch": 1.0,
        "voice_type": "narrator"
    }
    
    if element.type == "SCENE_HEADING":
        # Scene heading: voix plus lente, grave
        voice_params["rate"] = 0.9
        voice_params["pitch"] = 0.8
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 1000  # ms
        
    elif element.type == "ACTION":
        # Action: voix normale
        voice_params["rate"] = 1.0
        voice_params["pitch"] = 1.0
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 500
        
    elif element.type == "CHARACTER":
        # Ne pas lire le nom du personnage, juste noter qui parle
        voice_params["skip"] = True
        
    elif element.type == "DIALOGUE":
        # Dialogue: adapter la voix au personnage
        if last_character and characters:
            char_info = characters.get(last_character, {})
            gender = char_info.get("gender") or guess_gender(last_character)
            
            if gender == "female":
                voice_params["pitch"] = 1.3
                voice_params["voice_type"] = "female"
            elif gender == "male":
                voice_params["pitch"] = 0.8
                voice_params["voice_type"] = "male"
            else:
                voice_params["pitch"] = 1.0
                voice_params["voice_type"] = "neutral"
        
        voice_params["rate"] = 1.1  # Dialogue légèrement plus rapide
        voice_params["pause_after"] = 300
        
    elif element.type == "PARENTHETICAL":
        # Parenthetical: voix plus douce, rapide
        voice_params["rate"] = 1.2
        voice_params["pitch"] = 1.1
        voice_params["volume"] = 0.7
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 200
        
    elif element.type == "TRANSITION":
        # Transition: voix grave, pause après
        voice_params["rate"] = 0.8
        voice_params["pitch"] = 0.7
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 1500
    
    return voice_params


@app.post("/tts/prepare")
async def prepare_tts(request: TTSRequestAdvanced):
    """
    Prépare les données pour la lecture vocale côté client (Web Speech API)
    
    Retourne une liste d'éléments avec les paramètres de voix pour chaque
    """
    try:
        # Construire le dictionnaire des personnages
        characters = {}
        if request.characters:
            for char in request.characters:
                characters[char.name.upper()] = {
                    "gender": char.gender,
                    "age": char.age,
                    "voice_id": char.voice_id
                }
        
        # Préparer les éléments avec les paramètres de voix
        tts_elements = []
        last_character = None
        
        for el in request.elements:
            voice_params = get_voice_for_element(el, characters, last_character)
            
            # Mettre à jour le dernier personnage
            if el.type == "CHARACTER":
                last_character = el.text.upper().split("(")[0].strip()
            
            # Ajouter l'élément avec ses paramètres
            tts_elements.append({
                "type": el.type,
                "text": el.text,
                "voice": voice_params,
                "character": last_character if el.type in ["DIALOGUE", "PARENTHETICAL"] else None
            })
        
        return {
            "success": True,
            "title": request.title,
            "elements": tts_elements,
            "total_elements": len(tts_elements)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================
# HEALTH CHECK
# ============================================

@app.get("/")
async def root():
    return {
        "service": "Screenplay Editor API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ============================================
# RUN (pour dev local)
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
