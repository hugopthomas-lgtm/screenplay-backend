"""
Screenplay Editor Backend
FastAPI server for FDX export, Text-to-Speech, and Scene Board AI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import httpx

app = FastAPI(
    title="Screenplay Editor API",
    description="Backend for Screenplay Editor - FDX export, TTS & Scene Board AI",
    version="2.0.0"
)

# CORS - autoriser les appels depuis Google Apps Script et l'extension Chrome
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Anthropic
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


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
    gender: Optional[str] = None
    age: Optional[str] = None
    voice_id: Optional[str] = None


class TTSRequestAdvanced(BaseModel):
    title: str
    elements: List[ScriptElement]
    characters: Optional[List[Character]] = None


class Scene(BaseModel):
    id: int
    heading: str
    content: str  # Tout le contenu de la scène (action, dialogue, etc.)


class SceneBoardRequest(BaseModel):
    title: str
    scenes: List[Scene]
    language: Optional[str] = "en"  # "en" ou "fr"


class ReorderRequest(BaseModel):
    title: str
    scene_order: List[int]  # Liste des IDs dans le nouvel ordre


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
    """Exporte un scénario au format FDX (Final Draft)"""
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
    """Retourne le contenu FDX en JSON (pour Apps Script)"""
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

FEMALE_NAMES = {
    "MARIE", "SOPHIE", "JULIE", "EMMA", "LÉA", "CHLOÉ", "CAMILLE", "SARAH",
    "LAURA", "CLARA", "ALICE", "ANNA", "EVA", "LISA", "MARY", "JANE",
    "OLIVIA", "AVA", "MIA", "EMILY", "ELLA", "LUCY", "GRACE"
}

MALE_NAMES = {
    "JEAN", "PIERRE", "PAUL", "JACQUES", "MICHEL", "MARC", "LUC", "THOMAS",
    "NICOLAS", "ANTOINE", "LOUIS", "HUGO", "LUCAS", "JOHN", "JAMES", "DAVID",
    "MICHAEL", "WILLIAM", "RICHARD", "ROBERT", "CHARLES", "JOSEPH"
}


def guess_gender(name: str) -> str:
    """Devine le genre d'un personnage basé sur son nom"""
    clean_name = name.upper().split()[0]
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
    """Retourne les paramètres de voix pour un élément"""
    
    voice_params = {
        "rate": 1.0,
        "pitch": 1.0,
        "voice_type": "narrator"
    }
    
    if element.type == "SCENE_HEADING":
        voice_params["rate"] = 0.9
        voice_params["pitch"] = 0.8
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 1000
        
    elif element.type == "ACTION":
        voice_params["rate"] = 1.0
        voice_params["pitch"] = 1.0
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 500
        
    elif element.type == "CHARACTER":
        voice_params["skip"] = True
        
    elif element.type == "DIALOGUE":
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
        
        voice_params["rate"] = 1.1
        voice_params["pause_after"] = 300
        
    elif element.type == "PARENTHETICAL":
        voice_params["rate"] = 1.2
        voice_params["pitch"] = 1.1
        voice_params["volume"] = 0.7
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 200
        
    elif element.type == "TRANSITION":
        voice_params["rate"] = 0.8
        voice_params["pitch"] = 0.7
        voice_params["voice_type"] = "narrator"
        voice_params["pause_after"] = 1500
    
    return voice_params


@app.post("/tts/prepare")
async def prepare_tts(request: TTSRequestAdvanced):
    """Prépare les données pour la lecture vocale côté client"""
    try:
        characters = {}
        if request.characters:
            for char in request.characters:
                characters[char.name.upper()] = {
                    "gender": char.gender,
                    "age": char.age,
                    "voice_id": char.voice_id
                }
        
        tts_elements = []
        last_character = None
        
        for el in request.elements:
            voice_params = get_voice_for_element(el, characters, last_character)
            
            if el.type == "CHARACTER":
                last_character = el.text.upper().split("(")[0].strip()
            
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
# SCENE BOARD AI
# ============================================

async def call_claude(prompt: str, system: str = None) -> str:
    """Appelle l'API Claude"""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        messages = [{"role": "user", "content": prompt}]
        
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": messages
        }
        
        if system:
            body["system"] = system
        
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json=body
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        
        data = response.json()
        return data["content"][0]["text"]


@app.post("/api/scene-board/analyze")
async def analyze_scenes(request: SceneBoardRequest):
    """
    Analyse les scènes avec Claude AI
    Retourne un résumé, les personnages, le ton pour chaque scène
    """
    try:
        # Construire le prompt
        scenes_text = ""
        for scene in request.scenes:
            scenes_text += f"\n\n--- SCENE {scene.id} ---\n{scene.heading}\n{scene.content}"
        
        lang = "French" if request.language == "fr" else "English"
        
        system_prompt = f"""You are a professional script analyst. Analyze screenplay scenes and provide structured insights.
Always respond in {lang}.
Return ONLY valid JSON, no markdown, no explanation."""

        user_prompt = f"""Analyze these scenes from the screenplay "{request.title}":

{scenes_text}

For each scene, provide:
1. A brief summary (1-2 sentences)
2. Characters present (list)
3. Emotional tone (1-2 words)
4. Story function (setup/confrontation/resolution/transition)
5. Time of day (from scene heading or content)

Return as JSON array:
[
  {{
    "id": 1,
    "summary": "...",
    "characters": ["..."],
    "tone": "...",
    "function": "...",
    "time": "..."
  }}
]"""

        result = await call_claude(user_prompt, system_prompt)
        
        # Parser le JSON
        import json
        # Nettoyer le résultat (enlever markdown si présent)
        clean_result = result.strip()
        if clean_result.startswith("```"):
            clean_result = clean_result.split("\n", 1)[1]
            clean_result = clean_result.rsplit("```", 1)[0]
        
        analysis = json.loads(clean_result)
        
        return {
            "success": True,
            "title": request.title,
            "analysis": analysis
        }
        
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse AI response: {str(e)}",
            "raw_response": result if 'result' in dir() else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/scene-board/suggest")
async def suggest_improvements(request: SceneBoardRequest):
    """
    Suggère des améliorations de structure
    """
    try:
        scenes_text = ""
        for scene in request.scenes:
            scenes_text += f"\n--- SCENE {scene.id}: {scene.heading} ---\n"
        
        lang = "French" if request.language == "fr" else "English"
        
        system_prompt = f"""You are a professional screenwriting consultant. 
Analyze screenplay structure and suggest improvements.
Always respond in {lang}.
Return ONLY valid JSON."""

        user_prompt = f"""Review the scene order for "{request.title}":

{scenes_text}

Provide:
1. Overall structure assessment (3-act structure, pacing)
2. Suggested scene reordering (if any)
3. Missing story beats
4. Pacing issues

Return as JSON:
{{
  "assessment": "...",
  "suggested_order": [1, 2, 3, ...] or null if current order is good,
  "missing_beats": ["..."],
  "pacing_notes": "..."
}}"""

        result = await call_claude(user_prompt, system_prompt)
        
        import json
        clean_result = result.strip()
        if clean_result.startswith("```"):
            clean_result = clean_result.split("\n", 1)[1]
            clean_result = clean_result.rsplit("```", 1)[0]
        
        suggestions = json.loads(clean_result)
        
        return {
            "success": True,
            "suggestions": suggestions
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================
# SCENE BOARD PAGE
# ============================================

@app.get("/sceneboard", response_class=HTMLResponse)
async def sceneboard_page():
    """Sert la page Scene Board"""
    html_path = os.path.join(os.path.dirname(__file__), "sceneboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return """
        <html>
        <body>
        <h1>Scene Board</h1>
        <p>sceneboard.html not found. Please deploy the file.</p>
        </body>
        </html>
        """


# ============================================
# HEALTH CHECK
# ============================================

@app.get("/")
async def root():
    return {
        "service": "Screenplay Editor API",
        "version": "2.0.0",
        "status": "running",
        "features": ["fdx_export", "tts", "scene_board_ai"]
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "anthropic_configured": ANTHROPIC_API_KEY is not None
    }


# ============================================
# RUN (pour dev local)
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
