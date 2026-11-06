import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import errors, types
import time, random
from datetime import datetime
import pypdf
import os
import urllib.parse
import markdown
from weasyprint import HTML, CSS
from openai import OpenAI, APITimeoutError
import base64
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import re
import json

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="AI Public Aréna", layout="wide")

# --- SLOVNÍK PŘEKLADŮ ---
TEXTS = {
    "cs": {
        "lang_name": "Jazyk / Language",
        "nav": "🧭 Navigace",
        "nav_arena": "⚔️ Debatní Aréna",
        "nav_help": "❓ Nápověda a návody",
        "settings": "⚙️ Nastavení debaty",
        "api_keys": "🔑 API klíče",
        "save_keys": "💾 Uložit klíče do prohlížeče",
        "save_keys_success": "✅ Klíče byly uloženy do paměti prohlížeče.",
        "provider_select": "Poskytovatel",
        "rounds": "Počet výměn názorů (kol)",
        "persona_a": "Osobnost A",
        "persona_b": "Osobnost B",
        "name": "Jméno",
        "input_type": "Způsob zadání instrukcí",
        "manual": "Ručně",
        "upload": "Nahrát soubor",
        "instructions": "Instrukce",
        "moderator": "Moderátor (Rozhodčí)",
        "topic_type": "Způsob zadání tématu:",
        "topic_text": "Téma diskuze:",
        "topic_file": "Název diskuze (pro export):",
        "upload_topic": "Nahrajte podklady pro diskuzi (PDF, MD, TXT)",
        "start_debate": "🚀 Spustit diskuzi",
        "no_key_error": "⚠️ **Nemáte zadán žádný API klíč!** K provozu arény bohatě stačí jeden API klíč. Pokud žádný nemáte, nejjednodušší je [**Google Gemini**](https://aistudio.google.com/app/apikey) (stačí vám k tomu jen běžný Google účet).",
        "tip": "💡 **Tip:** K provozu arény bohatě stačí **jeden API klíč**. Pokud žádný nemáte, nejjednodušší je [**Google Gemini**](https://aistudio.google.com/app/apikey) (stačí vám k tomu jen běžný Google účet).",
        "debate_title": "🗣️ AI Public Aréna",
        "debate_caption": "Automatizovaná diskuze dvou AI osobností s dynamickým výběrem modelů.",
        "judge": "Rozhodčí",
        "new_debate": "🔄 Nová debata",
        "critique_title": "🔍 Nezávislá kritika diskuze",
        "critique_caption": "Nechte diskuzi a verdikt rozhodčího posoudit další nezávislou AI.",
        "start_critique": "Spustit nezávislou kritiku",
        "tab_api": "🤖 Přímé API (automatické)",
        "tab_ext": "🌐 Externí AI chat (manuální)",
        "critique_gen": "🚀 Generovat kritiku pomocí",
        "ext_info": "💡 **Externí chat:** Zkopírujte prompt, přiložte PDF diskuzi a nechte AI vyhodnotit. Poté výsledek vložte zpět.",
        "ext_step1": "1. 📄 Stáhnout PDF diskuze",
        "ext_step2": "2. Otevřete váš oblíbený AI chat:",
        "ext_step3": "3. Zkopírujte prompt a vložte ho do chatu (spolu s PDF):",
        "ext_step4": "4. Vložte sem výsledek kritiky z externího chatu:",
        "save_critique": "💾 Uložit kritiku na R2",
        "ready_critique": "✅ Hotová kritika",
        "dl_critique_md": "📥 Kritika (.md)",
        "dl_critique_pdf": "📄 Kritika (.pdf)",
        "preview_critique": "📄 Náhled kritiky",
        "dl_md": "📥 Stáhnout jako Markdown (.md)",
        "dl_pdf": "📄 Stáhnout jako PDF (.pdf)",
        "h_title": "📖 Nápověda a návody",
        "h_sub": "Proč používat AI Public Arénu? (3 hlavní výhody)",
        "h_p1": "**Odstraňuje jednostranný pohled jedné AI:** Klasický chat Vám řekne jen jeden názor. Aréna postaví proti sobě dva různé agenty s odlišnými osobnostmi, což odhalí slabiny v argumentech mnohem lépe.",
        "h_p2": "**Objektivní rozhodčí:** Po skončení debaty nastupuje třetí nezávislá AI (rozhodčí), která má za úkol nestranně zvážit argumenty obou stran a vynést jasný verdikt.",
        "h_p3": "**Hlubší analýza:** Díky automatickému střídání replik a možnosti nahrát podkladové dokumenty (PDF) jde o precizní nástroj pro analýzu složitých témat (politika, filozofie, vědecké studie).",
        "h_start": "## 🚀 Jak začít\nK provozu aplikace **bohatě stačí jeden API klíč**. Nemusíte zakládat účty u všech poskytovatelů.",
        "h_start_gemini": "*   **Nejjednodušší volba je Google Gemini.** Pokud máte účet Google (Gmail), máte pravděpodobně přístup i do Google AI Studia, kde klíč získáte během 30 vteřin zdarma.",
        "h_start_other": "*   Ostatní klíče (Mistral, NVIDIA) jsou zde jako alternativa pro specifické modely nebo jako záloha, pokud by Vám došly limity.",
        "h_start_save": "*   **Tip:** V postranním panelu můžete kliknout na tlačítko \"Uložit klíče do prohlížeče\". Vaše klíče se bezpečně uloží do paměti vašeho prohlížeče a při příští návštěvě se automaticky vyplní.",
        "exp_gemini": "🔵 Google Gemini (Nejjednodušší na získání)",
        "exp_nvidia": "🟢 NVIDIA NIM (Rychlost a velké modely)",
        "exp_mistral": "🟠 Mistral AI (Alternativa)",
        "exp_crit": "🟣 Nezávislá kritika – jak to funguje",
        # --- NOVÉ KLÍČE ---
        "preset_label": "🎬 Rychlý preset",
        "preset_help": "Vyberte hotový scénář pro rychlý start. Volba 'Vlastní' nic nemění – vše si nastavíte sami.",
        "preset_academic": "🎓 Akademická debata",
        "preset_aggressive": "⚔️ Agresivní souboj",
        "preset_consensus": "🤝 Hledání konsenzu",
        "preset_factcheck": "🔬 Fact-check duel",
        "preset_brainstorm": "💡 Brainstorming",
        "preset_dissenter": "🔥 Dissenter (neshoda jako cíl)",
        "preset_custom": "✏️ Vlastní nastavení",
        "temperament_label": "Temperament",
        "temperament_neutral": "Neutrální / věcný",
        "temperament_passionate": "Vášnivý / emotivní",
        "temperament_ironic": "Ironický / sarkastický",
        "temperament_empathetic": "Empatický / naslouchající",
        "temperament_aggressive": "Agresivní / konfrontační",
        "expertise_label": "Expertíza",
        "expertise_layman": "Laik",
        "expertise_student": "Student",
        "expertise_expert": "Odborník",
        "expertise_professor": "Profesor",
        "expertise_visionary": "Vizionář",
        "random_button": "🎲 Náhodně",
        "response_length_label": "Délka odpovědi",
        "length_short": "💬 Krátká (1–2 věty)",
        "length_medium": "📝 Střední (1 odstavec)",
        "length_long": "📄 Dlouhá (2–3 odstavce)",
        "length_detailed": "📚 Detailní (bez omezení)",
        "debate_goal_label": "🎯 Cíl debaty",
        "goal_verdict": "⚖️ Verdikt (vybrat vítěze)",
        "goal_consensus": "🤝 Konsenzus (shrnout shody)",
        "goal_dissenter": "🔥 Dissenter (zvýraznit neshodu)",
        "rules_label": "📏 Specifická pravidla",
        "rule_no_repeat": "Neopakovat již řečené argumenty",
        "rule_facts_only": "Jen fakta, žádné spekulace",
        "rule_cite_sources": "Citovat zdroje a data",
        "rule_admit_ignorance": "Přiznat, když něco nevím",
        "rule_allow_fiction": "Smí používat fiktivní data (roleplay)",
        "rule_allow_mind_change": "Smí změnit názor, pokud ho protivník přesvědčí",
        "rule_no_personal": "Vyhýbat se osobním útokům",
        "rule_end_question": "Každá replika končí otázkou na protivníka",
        "advanced_settings": "⚙️ Pokročilé nastavení",
        "memory_limit_label": "Paměť kontextu (posledních N replik)",
    },
    "en": {
        "lang_name": "Language / Jazyk",
        "nav": "🧭 Navigation",
        "nav_arena": "⚔️ Debate Arena",
        "nav_help": "❓ Help & Guides",
        "settings": "⚙️ Debate Settings",
        "api_keys": "🔑 API Keys",
        "save_keys": "💾 Save Keys to Browser",
        "save_keys_success": "✅ Keys have been saved to browser memory.",
        "provider_select": "Provider",
        "rounds": "Number of exchanges (rounds)",
        "persona_a": "Persona A",
        "persona_b": "Persona B",
        "name": "Name",
        "input_type": "How to input instructions",
        "manual": "Manual",
        "upload": "Upload file",
        "instructions": "Instructions",
        "moderator": "Moderator (Judge)",
        "topic_type": "How to input topic:",
        "topic_text": "Debate topic:",
        "topic_file": "Debate name (for export):",
        "upload_topic": "Upload debate materials (PDF, MD, TXT)",
        "start_debate": "🚀 Start Debate",
        "no_key_error": "⚠️ **No API key provided!** One API key is enough to run the arena. If you don't have one, the easiest is [**Google Gemini**](https://aistudio.google.com/app/apikey) (all you need is a standard Google account).",
        "tip": "💡 **Tip:** **One API key is enough** to run the arena. If you don't have one, the easiest is [**Google Gemini**](https://aistudio.google.com/app/apikey) (all you need is a standard Google account).",
        "debate_title": "🗣️ AI Public Arena",
        "debate_caption": "Automated discussion of two AI personas with dynamic model selection.",
        "judge": "Judge",
        "new_debate": "🔄 New Debate",
        "critique_title": "🔍 Independent Critique",
        "critique_caption": "Let another independent AI evaluate the debate and the judge's verdict.",
        "start_critique": "Start Independent Critique",
        "tab_api": "🤖 Direct API (automatic)",
        "tab_ext": "🌐 External AI chat (manual)",
        "critique_gen": "🚀 Generate critique using",
        "ext_info": "💡 **External chat:** Copy the prompt, attach the PDF debate, and let the AI evaluate it. Then paste the result back.",
        "ext_step1": "1. 📄 Download PDF debate",
        "ext_step2": "2. Open your favorite AI chat:",
        "ext_step3": "3. Copy the prompt and paste it into the chat (along with the PDF):",
        "ext_step4": "4. Paste the critique result from the external chat here:",
        "save_critique": "💾 Save Critique to R2",
        "ready_critique": "✅ Critique Ready",
        "dl_critique_md": "📥 Critique (.md)",
        "dl_critique_pdf": "📄 Critique (.pdf)",
        "preview_critique": "📄 Critique Preview",
        "dl_md": "📥 Download as Markdown (.md)",
        "dl_pdf": "📄 Download as PDF (.pdf)",
        "h_title": "📖 Help & Guides",
        "h_sub": "Why use AI Public Arena? (3 Main Benefits)",
        "h_p1": "**Removes the single-AI bias:** A classic chat gives you only one perspective. The Arena pits two different agents with distinct personas against each other, exposing weaknesses in arguments much better.",
        "h_p2": "**Objective Judge:** After the debate ends, a third independent AI (judge) steps in to impartially weigh the arguments of both sides and deliver a clear verdict.",
        "h_p3": "**Deeper Analysis:** Thanks to automatic turn-taking and the ability to upload supporting documents (PDF), it's a precise tool for analyzing complex topics (politics, philosophy, scientific studies).",
        "h_start": "## 🚀 How to start\n**One API key is more than enough** to run the app. You don't need to create accounts with all providers.",
        "h_start_gemini": "*   **The easiest choice is Google Gemini.** If you have a Google account (Gmail), you likely have access to Google AI Studio, where you can get a free key in 30 seconds.",
        "h_start_other": "*   Other keys (Mistral, NVIDIA) are here as an alternative for specific models or as a backup if you run out of limits.",
        "h_start_save": "*   **Tip:** In the sidebar, you can click \"Save Keys to Browser\". Your keys will be securely saved in your browser's memory and automatically filled in on your next visit.",
        "exp_gemini": "🔵 Google Gemini (Easiest to get)",
        "exp_nvidia": "🟢 NVIDIA NIM (Speed and large models)",
        "exp_mistral": "🟠 Mistral AI (Alternative)",
        "exp_crit": "🟣 Independent Critique – How it works",
        # --- NEW KEYS ---
        "preset_label": "🎬 Quick Preset",
        "preset_help": "Choose a preset for a quick start. 'Custom' does nothing – you set everything yourself.",
        "preset_academic": "🎓 Academic Debate",
        "preset_aggressive": "⚔️ Aggressive Duel",
        "preset_consensus": "🤝 Consensus Seeking",
        "preset_factcheck": "🔬 Fact-check Duel",
        "preset_brainstorm": "💡 Brainstorming",
        "preset_dissenter": "🔥 Dissenter (disagreement as goal)",
        "preset_custom": "✏️ Custom",
        "temperament_label": "Temperament",
        "temperament_neutral": "Neutral / factual",
        "temperament_passionate": "Passionate / emotional",
        "temperament_ironic": "Ironic / sarcastic",
        "temperament_empathetic": "Empathetic / listening",
        "temperament_aggressive": "Aggressive / confrontational",
        "expertise_label": "Expertise",
        "expertise_layman": "Layperson",
        "expertise_student": "Student",
        "expertise_expert": "Expert",
        "expertise_professor": "Professor",
        "expertise_visionary": "Visionary",
        "random_button": "🎲 Randomize",
        "response_length_label": "Response length",
        "length_short": "💬 Short (1–2 sentences)",
        "length_medium": "📝 Medium (1 paragraph)",
        "length_long": "📄 Long (2–3 paragraphs)",
        "length_detailed": "📚 Detailed (no limit)",
        "debate_goal_label": "🎯 Debate goal",
        "goal_verdict": "⚖️ Verdict (pick a winner)",
        "goal_consensus": "🤝 Consensus (summarize agreements)",
        "goal_dissenter": "🔥 Dissenter (highlight disagreement)",
        "rules_label": "📏 Specific rules",
        "rule_no_repeat": "Do not repeat arguments already made",
        "rule_facts_only": "Facts only, no speculation",
        "rule_cite_sources": "Cite sources and data",
        "rule_admit_ignorance": "Admit when I don't know something",
        "rule_allow_fiction": "May use fictional data (roleplay)",
        "rule_allow_mind_change": "May change opinion if opponent convinces me",
        "rule_no_personal": "Avoid personal attacks",
        "rule_end_question": "Every reply ends with a question to the opponent",
        "advanced_settings": "⚙️ Advanced Settings",
        "memory_limit_label": "Context memory (last N replies)",
    }
}

# --- NASTAVENÍ JAZYKA ---
if "lang" not in st.session_state:
    st.session_state.lang = "cs"

def t(key):
    return TEXTS[st.session_state.lang].get(key, key)

# --- NAČTENÍ KLÍČŮ Z PROHLÍŽEČE (LOCAL STORAGE) ---
_restored_any_key = False
if "g_key" in st.query_params:
    st.session_state.gemini_key = st.query_params["g_key"]
    _restored_any_key = True
if "n_key" in st.query_params:
    st.session_state.nim_key = st.query_params["n_key"]
    _restored_any_key = True
if "m_key" in st.query_params:
    st.session_state.mistral_key = st.query_params["m_key"]
    _restored_any_key = True
if _restored_any_key:
    st.query_params.clear()

# --- KONSTANTY PRO NOVÉ PARAMETRY ---
PRESET_KEYS = ["academic", "aggressive", "consensus", "factcheck", "brainstorm", "dissenter", "custom"]
TEMPERAMENT_KEYS = ["neutral", "passionate", "ironic", "empathetic", "aggressive"]
EXPERTISE_KEYS = ["layman", "student", "expert", "professor", "visionary"]
LENGTH_KEYS = ["short", "medium", "long", "detailed"]
GOAL_KEYS = ["verdict", "consensus", "dissenter"]
RULE_KEYS = ["no_repeat", "facts_only", "cite_sources", "admit_ignorance",
             "allow_fiction", "allow_mind_change", "no_personal", "end_question"]

# --- DEFINICE PRESETŮ ---
PRESETS = {
    "academic": {
        "temperament_a": "neutral", "temperament_b": "neutral",
        "expertise_a": "professor", "expertise_b": "professor",
        "response_length": "medium", "debate_goal": "verdict",
        "debate_rules": ["no_repeat", "cite_sources", "admit_ignorance"],
    },
    "aggressive": {
        "temperament_a": "passionate", "temperament_b": "aggressive",
        "expertise_a": "expert", "expertise_b": "expert",
        "response_length": "short", "debate_goal": "verdict",
        "debate_rules": ["no_repeat", "no_personal", "end_question"],
    },
    "consensus": {
        "temperament_a": "empathetic", "temperament_b": "empathetic",
        "expertise_a": "expert", "expertise_b": "expert",
        "response_length": "long", "debate_goal": "consensus",
        "debate_rules": ["no_repeat", "allow_mind_change", "no_personal"],
    },
    "factcheck": {
        "temperament_a": "neutral", "temperament_b": "neutral",
        "expertise_a": "expert", "expertise_b": "expert",
        "response_length": "medium", "debate_goal": "verdict",
        "debate_rules": ["facts_only", "cite_sources", "admit_ignorance", "no_repeat"],
    },
    "brainstorm": {
        "temperament_a": "passionate", "temperament_b": "passionate",
        "expertise_a": "visionary", "expertise_b": "visionary",
        "response_length": "short", "debate_goal": "consensus",
        "debate_rules": ["allow_fiction", "end_question"],
    },
    "dissenter": {
        "temperament_a": "passionate", "temperament_b": "passionate",
        "expertise_a": "expert", "expertise_b": "expert",
        "response_length": "medium", "debate_goal": "dissenter",
        "debate_rules": ["no_repeat", "facts_only", "end_question"],
    },
}

# --- PROMPTY PRO JEDNOTLIVÉ VLASTNOSTI ---
TEMPERAMENT_PROMPTS = {
    "cs": {
        "neutral": "",
        "passionate": "Vyjadřuj se vášnivě a s emocemi. Používej silná slova a živé metafory. Tvé argumenty mají jiskru.",
        "ironic": "Používej ironii a jemný sarkasmus. Shazuj argumenty oponenta s nadhledem, ale zůstaň věcný.",
        "empathetic": "Nejprve pochop a oceni stanovisko oponenta, teprve pak argumentuj. Buď vstřícný a hledej průsečíky.",
        "aggressive": "Buď konfrontační a asertivní. Útoč na slabá místa argumentů, ale vyhýbej se osobním útokům.",
    },
    "en": {
        "neutral": "",
        "passionate": "Express yourself passionately and emotionally. Use strong words and vivid metaphors. Your arguments have spark.",
        "ironic": "Use irony and mild sarcasm. Tear down your opponent's arguments with perspective, but stay factual.",
        "empathetic": "First understand and acknowledge your opponent's position, then argue. Be welcoming and seek common ground.",
        "aggressive": "Be confrontational and assertive. Attack the weak points of arguments, but avoid personal attacks.",
    }
}

EXPERTISE_PROMPTS = {
    "cs": {
        "layman": "Mluv jako laik – nechápej hluboké detaily, ptej se, používej jednoduchý jazyk a každodenní příklady.",
        "student": "Mluv jako student – základy ovládáš, ale občas tápeš, učíš se a kladeš otázky.",
        "expert": "Mluv jako odborník – argumentuj fundovaně, používej koncepty, ale nezahlcuj posluchače.",
        "professor": "Mluv jako profesor – akademicky, strukturovaně, s odkazy na širší kontext a výzkum.",
        "visionary": "Mluv jako vizionář – kreativně, mysli mimo rámec, přinášej nové perspektivy a neotřelé nápady.",
    },
    "en": {
        "layman": "Speak as a layperson – don't grasp deep details, ask questions, use simple language and everyday examples.",
        "student": "Speak as a student – you know the basics but sometimes struggle, you learn and ask questions.",
        "expert": "Speak as an expert – argue with authority, use concepts, but don't overwhelm the listener.",
        "professor": "Speak as a professor – academically, structured, with references to broader context and research.",
        "visionary": "Speak as a visionary – creatively, think outside the box, bring new perspectives and fresh ideas.",
    }
}

LENGTH_PROMPTS = {
    "cs": {
        "short": "Odpovídej velmi krátce – maximálně 1–2 věty. Buď úderný.",
        "medium": "Odpovídej v jednom odstavci (3–5 vět).",
        "long": "Odpovídej ve 2–3 odstavcích.",
        "detailed": "Odpovídej detailně, bez omezení délky.",
    },
    "en": {
        "short": "Reply very briefly – at most 1–2 sentences. Be punchy.",
        "medium": "Reply in one paragraph (3–5 sentences).",
        "long": "Reply in 2–3 paragraphs.",
        "detailed": "Reply in detail, no length limit.",
    }
}

RULE_PROMPTS = {
    "cs": {
        "no_repeat": "Neopakuj již řečené argumenty. Vždy přines nový úhel pohledu.",
        "facts_only": "Používej jen fakta a ověřitelné informace. Vyhýbej se spekulacím.",
        "cite_sources": "Pokud můžeš, cituj zdroje, konkrétní data nebo výzkumy.",
        "admit_ignorance": "Když něco nevíš, přiznej to otevřeně. Nevymýšlej si.",
        "allow_fiction": "Můžeš používat fiktivní data nebo scénáře pro ilustraci (roleplay).",
        "allow_mind_change": "Můžeš změnit názor, pokud tě protivník přesvědčí. Ber to jako sílu, ne slabost.",
        "no_personal": "Vyhýbej se osobním útokům. Útoč na argumenty, ne na osobu.",
        "end_question": "Každou repliku zakonči otázkou na protivníka.",
    },
    "en": {
        "no_repeat": "Do not repeat arguments already made. Always bring a new angle.",
        "facts_only": "Use only facts and verifiable information. Avoid speculation.",
        "cite_sources": "If possible, cite sources, concrete data or research.",
        "admit_ignorance": "When you don't know something, admit it openly. Don't make things up.",
        "allow_fiction": "You may use fictional data or scenarios for illustration (roleplay).",
        "allow_mind_change": "You may change your mind if your opponent convinces you. Treat it as strength, not weakness.",
        "no_personal": "Avoid personal attacks. Attack the arguments, not the person.",
        "end_question": "End every reply with a question to your opponent.",
    }
}

JUDGE_GOAL_PROMPTS = {
    "cs": {
        "consensus": "TVŮJ CÍL NENÍ VYBRAT VÍTĚZE. Identifikuj, na čem se obě strany shodly, shrň společné závěry a jasně označ body, kde neshoda přetrvává. Formuluj doporučení pro další diskuzi.",
        "dissenter": "TVŮJ CÍL NENÍ VYBRAT VÍTĚZE. Popiš, v čem přesně se strany rozcházejí a proč (odlišné hodnoty, odlišná data, odlišné priority). Označ otázky, které zůstaly nerozhodnuté, a navrhni, co by bylo potřeba k jejich vyřešení.",
    },
    "en": {
        "consensus": "YOUR GOAL IS NOT TO PICK A WINNER. Identify what both sides agreed on, summarize common conclusions, and clearly mark points where disagreement persists. Formulate recommendations for further discussion.",
        "dissenter": "YOUR GOAL IS NOT TO PICK A WINNER. Describe exactly where the parties diverge and why (different values, different data, different priorities). Mark questions that remained unresolved and suggest what would be needed to resolve them.",
    }
}

# --- 1. INICIALIZACE PAMĚTI ---
if "debate_active" not in st.session_state: st.session_state.debate_active = False
if "full_history" not in st.session_state: st.session_state.full_history = []
if "final_summary" not in st.session_state: st.session_state.final_summary = ""
if "model_mod_used" not in st.session_state: st.session_state.model_mod_used = ""
if "current_topic" not in st.session_state: st.session_state.current_topic = ""
if "md_content" not in st.session_state: st.session_state.md_content = ""
if "pdf_bytes" not in st.session_state: st.session_state.pdf_bytes = b""
if "file_base_name" not in st.session_state: st.session_state.file_base_name = "debata"

if "critique_md" not in st.session_state: st.session_state.critique_md = ""
if "critique_pdf" not in st.session_state: st.session_state.critique_pdf = b""
if "critique_base" not in st.session_state: st.session_state.critique_base = ""
if "show_critique_ui" not in st.session_state: st.session_state.show_critique_ui = False

for key in ["gemini_key", "nim_key", "mistral_key"]:
    if key not in st.session_state: st.session_state[key] = ""

if "local_storage_checked" not in st.session_state:
    if not st.session_state.gemini_key and not st.session_state.nim_key and not st.session_state.mistral_key:
        components.html("""
        <script>
            const g = localStorage.getItem('arena_gemini');
            const n = localStorage.getItem('arena_nim');
            const m = localStorage.getItem('arena_mistral');
            if (g || n || m) {
                const url = new URL(window.parent.location.href);
                if (g) url.searchParams.set('g_key', g);
                if (n) url.searchParams.set('n_key', n);
                if (m) url.searchParams.set('m_key', m);
                window.parent.location.href = url.toString();
            }
        </script>
        """, height=0)
    st.session_state.local_storage_checked = True

form_defaults = {
    "role_a_name": "", "role_a_prompt": "", "provider_a": "Gemini", "input_type_a": "manual",
    "role_b_name": "", "role_b_prompt": "", "provider_b": "Gemini", "input_type_b": "manual",
    "provider_mod": "Gemini", "topic_input": "", "max_rounds": 4,
    "topic_input_type": "manual", "topic_document_text": "", "topic_summary": "",
    "uploaded_files_hash": "",
    # Nové parametry – výchozí hodnoty odpovídají presetu "academic"
    "preset_select": "academic",
    "temperament_a": "neutral", "temperament_b": "neutral",
    "expertise_a": "professor", "expertise_b": "professor",
    "response_length": "medium", "debate_goal": "verdict",
    "debate_rules": ["no_repeat", "cite_sources", "admit_ignorance"],
    "memory_limit": 10,
}
for key, default in form_defaults.items():
    if key not in st.session_state: st.session_state[key] = default

# --- 2. POMOCNÉ FUNKCE ---
def extract_text_from_file(uploaded_file):
    if uploaded_file is None: return ""
    file_extension = uploaded_file.name.split('.')[-1].lower()
    try:
        if file_extension == 'pdf':
            pdf_reader = pypdf.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                if page.extract_text(): text += page.extract_text() + "\n"
            return text.strip()
        else:
            return uploaded_file.read().decode("utf-8").strip()
    except Exception as e:
        st.error(f"Error reading file {uploaded_file.name}: {e}")
        return ""

def generate_pdf(text_content):
    html_body = markdown.markdown(text_content, extensions=['tables', 'nl2br'])
    css_style = """
    @page { size: A4; margin: 2cm; @bottom-center { content: "Page " counter(page) " of " counter(pages); font-size: 9pt; color: #666; } }
    body { font-family: 'DejaVu Sans', sans-serif; font-size: 11pt; line-height: 1.5; color: #333; }
    h1 { color: #1a365d; font-size: 22pt; border-bottom: 2px solid #3182ce; padding-bottom: 5px; margin-top: 25px; }
    h2 { color: #2c5282; font-size: 16pt; margin-top: 20px; }
    h3 { color: #2b6cb0; font-size: 13pt; margin-top: 15px; }
    p { margin-bottom: 10px; text-align: justify; }
    small { color: #718096; font-size: 9pt; display: block; margin-top: 5px; font-style: italic; }
    blockquote { border-left: 4px solid #cbd5e0; padding-left: 15px; color: #4a5568; font-style: italic; background-color: #f7fafc; padding: 10px 15px; margin: 10px 0; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 10pt; }
    th, td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
    th { background-color: #edf2f7; font-weight: bold; color: #2d3748; }
    tr:nth-child(even) { background-color: #f7fafc; }
    """
    full_html = f"<!DOCTYPE html><html lang='cs'><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
    try:
        return HTML(string=full_html).write_pdf(stylesheets=[CSS(string=css_style)])
    except Exception as e:
        st.error(f"PDF generation error: {e}")
        return b""

@st.cache_resource
def get_r2_client():
    return boto3.client(
        service_name="s3",
        endpoint_url=f"https://{st.secrets['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=st.secrets["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", request_checksum_calculation="when_required"),
    )

def get_next_counter():
    s3 = get_r2_client()
    bucket = st.secrets["R2_BUCKET_NAME"]
    current = 0
    try:
        obj = s3.get_object(Bucket=bucket, Key="counter.txt")
        current = int(obj["Body"].read().decode("utf-8").strip())
    except Exception: pass
    next_val = current + 1
    s3.put_object(Bucket=bucket, Key="counter.txt", Body=str(next_val).encode("utf-8"))
    return f"{next_val:05d}"

def generate_filename_from_topic(topic, call_ai_func, available_providers):
    priority = [p for p in ["Gemini", "Mistral", "NVIDIA NIM"] if p in available_providers]
    if not priority: return "debata"

    prompt = f"Based on the topic, generate a short filename (max 7 words, no diacritics, only letters/numbers/underscores). Topic: '{topic}'"
    system_prompt = "Reply only with the filename, nothing else."

    for provider in priority:
        try:
            raw_name, _ = call_ai_func(system_prompt, prompt, provider)
            clean = re.sub(r"[^a-z0-9_]+", "_", raw_name.strip().lower())
            clean = re.sub(r"_+", "_", clean).strip("_")
            if clean: return "_".join(clean.split("_")[:7])
        except Exception: continue
    return "debata"

# --- ROZŠÍŘENÍ PROMPTŮ O VLASTNOSTI ---
def enhance_role_prompt(base_prompt, temperament, expertise, length, rules, lang):
    parts = [base_prompt]
    t_prompt = TEMPERAMENT_PROMPTS[lang].get(temperament, "")
    if t_prompt: parts.append(t_prompt)
    e_prompt = EXPERTISE_PROMPTS[lang].get(expertise, "")
    if e_prompt: parts.append(e_prompt)
    l_prompt = LENGTH_PROMPTS[lang].get(length, "")
    if l_prompt: parts.append(l_prompt)
    for rule in rules:
        r_prompt = RULE_PROMPTS[lang].get(rule, "")
        if r_prompt: parts.append(r_prompt)
    return "\n\n".join(parts)

def build_judge_prompt(base_prompt, goal, lang):
    parts = [base_prompt]
    if goal in ("consensus", "dissenter"):
        goal_prompt = JUDGE_GOAL_PROMPTS[lang].get(goal, "")
        if goal_prompt: parts.append(goal_prompt)
    return "\n\n".join(parts)

# --- MODEL PREFERENCE (nezměněno) ---
GEMINI_PREFERRED = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash"]
NVIDIA_PREFERRED = ["nvidia/nemotron-3-ultra-550b-a55b"]
MISTRAL_PREFERRED = ["ministral-3b-2512", "ministral-8b-2512", "codestral-2508", "mistral-large-2512"]

def get_available_gemini_models(client):
    try:
        models = client.models.list()
        available = [m.name.replace('models/', '') for m in models if 'generateContent' in getattr(m, 'supported_generation_methods', [])]
        verified = [m for m in GEMINI_PREFERRED if m in available]
        return verified if verified else (available if available else GEMINI_PREFERRED)
    except Exception: return GEMINI_PREFERRED

def get_available_mistral_models(client):
    try:
        all_models = client.models.list()
        available_ids = [m.id for m in all_models.data if m.id]
        verified = [m for m in MISTRAL_PREFERRED if m in available_ids]
        return verified if verified else (available_ids[:3] if available_ids else MISTRAL_PREFERRED)
    except Exception: return MISTRAL_PREFERRED

def get_delay_for_provider(provider):
    if provider == "NVIDIA NIM": return 2.0
    if provider == "Gemini": return 6.0
    if provider == "Mistral": return 3.0
    return 2.0

def render_downloads():
    base_name = st.session_state.get("file_base_name", "debata")
    md_b64 = base64.b64encode(st.session_state.md_content.encode('utf-8')).decode('utf-8')
    pdf_b64 = base64.b64encode(st.session_state.pdf_bytes).decode('utf-8') if st.session_state.pdf_bytes else ""
    html_code = f"""
    <div style="display: flex; gap: 10px;">
        <a href="data:application/octet-stream;base64,{md_b64}" download="{base_name}.md" style="flex: 1; text-align: center; padding: 10px; background-color: #f0f2f6; color: #31333f; text-decoration: none; border-radius: 5px; border: 1px solid #d6d6d6; font-size: 16px;">{t('dl_md')}</a>
        <a href="data:application/pdf;base64,{pdf_b64}" download="{base_name}.pdf" style="flex: 1; text-align: center; padding: 10px; background-color: #ff4b4b; color: white; text-decoration: none; border-radius: 5px; font-size: 16px;">{t('dl_pdf')}</a>
    </div>
    """
    components.html(html_code, height=60)

# --- 2c. NEZÁVISLÁ KRITIKA ---
CRITIQUE_SYSTEM_PROMPT = (
    "Jsi nezávislý recenzent a odborník na kritické hodnocení diskuzí. "
    "Tvým úkolem je nestranně posoudit kvalitu diskuze a verdikt rozhodčího. "
    "Buď konkrétní, kritický a konstruktivní. Odpovídej v jazyce, ve kterém je vedena diskuze."
)

def build_critique_prompt(md_content, topic):
    return f"""Vyhodnoť mi tuto diskuzi. Její relevantnost a "recenzuj" verdikt rozhodčího.

**Téma diskuze:** {topic}

**Úkoly pro tebe:**
1. **Relevantnost:** Zhodnoť, zda diskuze skutečně odpovídá na zadané téma.
2. **Kvalita argumentace:** Posuď sílu argumentů obou stran – kde byly přesvědčivé, kde slabé?
3. **Recenze verdiktu:** Byl verdikt rozhodčího oprávněný? Bylo odůvodnění přesvědčivé?
4. **Silné a slabé stránky** obou diskutujících.
5. **Návrh vyváženějšího verdiktu**, pokud s ním nesouhlasíš.

**Text diskuze:**

{md_content}
"""

def call_critique_api(system_prompt, user_prompt, provider, keys):
    if provider == "Gemini":
        client = genai.Client(api_key=keys["gemini"], http_options=types.HttpOptions(timeout=180000))
        for model in get_available_gemini_models(client):
            try:
                r = client.models.generate_content(model=model, contents=f"{system_prompt}\n\n---\n\n{user_prompt}", config=types.GenerateContentConfig())
                if r.text and r.text.strip(): return r.text, model
            except Exception: pass
        raise Exception("Kritika přes Gemini selhala.")
    elif provider == "Mistral":
        client = OpenAI(api_key=keys["mistral"], base_url="https://api.mistral.ai/v1", timeout=180.0)
        for model in get_available_mistral_models(client):
            try:
                r = client.chat.completions.create(model=model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.7)
                if r.choices[0].message.content: return r.choices[0].message.content, model
            except Exception: pass
        raise Exception("Kritika přes Mistral selhala.")
    elif provider == "NVIDIA NIM":
        client = OpenAI(api_key=keys["nim"], base_url="https://integrate.api.nvidia.com/v1", timeout=180.0)
        for model in NVIDIA_PREFERRED:
            try:
                r = client.chat.completions.create(model=model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.7)
                if r.choices[0].message.content: return r.choices[0].message.content, model
            except Exception: pass
        raise Exception("Kritika přes NVIDIA selhala.")
    raise Exception("Neznámý poskytovatel.")

def generate_critique_md(critique_text, model_used, topic):
    ts = datetime.now().strftime('%d.%m.%Y %H:%M')
    return f"# Nezávislá kritika diskuze\n\n**Téma:** {topic}  \n**Datum:** {ts}  \n**Model kritika:** {model_used}\n\n---\n\n{critique_text}\n"

def save_critique_to_r2(base_name, md_content, pdf_bytes):
    try:
        s3 = get_r2_client()
        bucket = st.secrets["R2_BUCKET_NAME"]
        s3.put_object(Bucket=bucket, Key=f"VERDICT/markdown/{base_name}.md", Body=md_content.encode("utf-8"), ContentType="text/markdown")
        s3.put_object(Bucket=bucket, Key=f"VERDICT/pdf/{base_name}.pdf", Body=pdf_bytes, ContentType="application/pdf")
        return True, None
    except Exception as e: return False, str(e)

def save_critique_result(critique_text, model_used):
    base_name = f"{st.session_state.file_base_name}_kritika"
    md_content = generate_critique_md(critique_text, model_used, st.session_state.current_topic)
    pdf_bytes = generate_pdf(md_content)
    st.session_state.critique_md = md_content
    st.session_state.critique_pdf = pdf_bytes
    st.session_state.critique_base = base_name
    ok, err = save_critique_to_r2(base_name, md_content, pdf_bytes)
    return ok, err, base_name

def reset_critique_state():
    st.session_state.critique_md = ""
    st.session_state.critique_pdf = b""
    st.session_state.critique_base = ""
    st.session_state.show_critique_ui = False

def render_critique_ui(available_providers_list):
    if not st.session_state.md_content: return

    st.divider()
    st.subheader(t("critique_title"))
    st.caption(t("critique_caption"))

    def start_critique():
        st.session_state.show_critique_ui = True

    if not st.session_state.show_critique_ui and not st.session_state.critique_md:
        st.button(t("start_critique"), type="primary", use_container_width=True, on_click=start_critique)

    if not (st.session_state.show_critique_ui or st.session_state.critique_md): return

    components.html(
        """
        <script>
            setTimeout(function() {
                var main = window.parent.document.querySelector('.main');
                if (main) { main.scrollTop = main.scrollHeight; }
            }, 50);
        </script>
        """,
        height=0,
        width=0
    )

    tab_api, tab_ext = st.tabs([t("tab_api"), t("tab_ext")])

    with tab_api:
        if not available_providers_list:
            st.warning(t("no_key_error").replace("debate", "critique").replace("diskuze", "kritiky"))
        else:
            options = [f"{p} (API)" for p in available_providers_list]
            selected = st.selectbox(t("provider_select"), options, key="critique_api_provider")
            provider = selected.replace(" (API)", "")

            if st.button(f"{t('critique_gen')} {provider}", type="primary"):
                keys = {"gemini": st.session_state.gemini_key.strip(), "nim": st.session_state.nim_key.strip(), "mistral": st.session_state.mistral_key.strip()}
                with st.spinner(f"{provider}..."):
                    try:
                        critique_text, model_used = call_critique_api(CRITIQUE_SYSTEM_PROMPT, build_critique_prompt(st.session_state.md_content, st.session_state.current_topic), provider, keys)
                        ok, err, base_name = save_critique_result(critique_text, model_used)
                        if ok: st.success(f"✅ Saved to R2.")
                        else: st.warning(f"⚠️ Saved locally, but R2 failed: {err}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    with tab_ext:
        st.info(t("ext_info"))

        pdf_b64 = base64.b64encode(st.session_state.pdf_bytes).decode('utf-8') if st.session_state.pdf_bytes else ""
        st.markdown(f'<a href="data:application/pdf;base64,{pdf_b64}" download="{st.session_state.file_base_name}.pdf" style="display:block; text-align:center; padding:10px; background:#ff4b4b; color:white; text-decoration:none; border-radius:6px; font-weight:600;">{t("ext_step1")}</a>', unsafe_allow_html=True)

        st.markdown(f"**{t('ext_step2')}**")
        chats = {
            "ChatGPT": "https://chatgpt.com/", "Claude": "https://claude.ai/new",
            "Gemini": "https://gemini.google.com/app", "Perplexity": "https://www.perplexity.ai/",
            "DeepSeek": "https://chat.deepseek.com/", "Copilot": "https://copilot.microsoft.com/",
            "Le Chat (Mistral)": "https://chat.mistral.ai/chat"
        }
        cols = st.columns(4)
        for i, (name, url) in enumerate(chats.items()):
            cols[i % 4].markdown(f'<a href="{url}" target="_blank" style="display:block; text-align:center; padding:8px; background:#e2e8f0; color:#2d3748; text-decoration:none; border-radius:5px; margin-bottom:5px; font-size:14px;">{name}</a>', unsafe_allow_html=True)

        st.markdown(f"**{t('ext_step3')}**")
        if st.session_state.lang == "cs":
            prompt_for_ext = f"Přečti přiložené PDF s diskuzí na téma: '{st.session_state.current_topic}'. Proveď nezávislou kritiku: zhodnoť relevanci, kvalitu argumentace obou stran a recenzuj verdikt rozhodčího. Navrhni vyváženější verdikt, pokud s ním nesouhlasíš."
        else:
            prompt_for_ext = f"Read the attached PDF with the debate on the topic: '{st.session_state.current_topic}'. Provide an independent critique: evaluate the relevance, the quality of arguments on both sides, and review the judge's verdict. Propose a more balanced verdict if you disagree with it."
        st.code(prompt_for_ext, language=None)

        st.markdown(f"**{t('ext_step4')}**")
        pasted = st.text_area("Result:", height=150, key="critique_pasted_ext", label_visibility="collapsed", placeholder="Paste text here...")
        if st.button(t("save_critique"), key="btn_save_ext"):
            if pasted.strip():
                ok, err, base_name = save_critique_result(pasted, "External AI (manual)")
                if ok: st.success(f"✅ Saved as `VERDICT/.../{base_name}...`.")
                else: st.warning(f"⚠️ Saved locally, but R2 failed: {err}")
            else:
                st.error("Please paste the text first.")

    if st.session_state.critique_md:
        st.divider()
        st.subheader(t("ready_critique"))
        md_b64 = base64.b64encode(st.session_state.critique_md.encode('utf-8')).decode('utf-8')
        pdf_b64 = base64.b64encode(st.session_state.critique_pdf).decode('utf-8')

        st.markdown(
            f'<div style="display:flex; gap:10px; margin:10px 0;">'
            f'<a href="data:application/octet-stream;base64,{md_b64}" download="{st.session_state.critique_base}.md" style="flex:1; text-align:center; padding:10px; background:#f0f2f6; color:#31333f; text-decoration:none; border-radius:5px; border:1px solid #d6d6d6;">{t("dl_critique_md")}</a>'
            f'<a href="data:application/pdf;base64,{pdf_b64}" download="{st.session_state.critique_base}.pdf" style="flex:1; text-align:center; padding:10px; background:#ff4b4b; color:white; text-decoration:none; border-radius:5px;">{t("dl_critique_pdf")}</a>'
            f'</div>', unsafe_allow_html=True
        )
        with st.expander(t("preview_critique"), expanded=False):
            st.markdown(st.session_state.critique_md)


# --- CALLBACKY PRO PŘEPÍNAČE ---
def apply_preset_callback():
    preset = st.session_state.preset_select
    if preset == "custom" or preset not in PRESETS:
        return
    cfg = PRESETS[preset]
    st.session_state.temperament_a = cfg["temperament_a"]
    st.session_state.temperament_b = cfg["temperament_b"]
    st.session_state.expertise_a = cfg["expertise_a"]
    st.session_state.expertise_b = cfg["expertise_b"]
    st.session_state.response_length = cfg["response_length"]
    st.session_state.debate_goal = cfg["debate_goal"]
    st.session_state.debate_rules = list(cfg["debate_rules"])

def randomize_persona_a():
    st.session_state.temperament_a = random.choice(TEMPERAMENT_KEYS)
    st.session_state.expertise_a = random.choice(EXPERTISE_KEYS)

def randomize_persona_b():
    st.session_state.temperament_b = random.choice(TEMPERAMENT_KEYS)
    st.session_state.expertise_b = random.choice(EXPERTISE_KEYS)


# --- 3. POSTRANNÍ PANEL ---
with st.sidebar:
    def get_image_base64(path):
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception:
            return ""

    cz_b64 = get_image_base64("cz.png")
    gb_b64 = get_image_base64("gb.png")

    st.markdown(f"""
        <div style="display: flex; justify-content: center; align-items: center; gap: 15px; margin-top: 10px; margin-bottom: 20px;">
            <img src="data:image/png;base64,{cz_b64}" width="30" style="border-radius: 3px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">
            <img src="data:image/png;base64,{gb_b64}" width="30" style="border-radius: 3px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">
        </div>
    """, unsafe_allow_html=True)

    lang_choice = st.radio(t("lang_name"), ["Čeština", "English"], index=0 if st.session_state.lang == "cs" else 1, horizontal=True)
    st.session_state.lang = "cs" if "Čeština" in lang_choice else "en"

    st.divider()
    st.header(t("nav"))
    app_mode = st.radio(t("nav"), [t("nav_arena"), t("nav_help")], index=0)
    st.divider()

    if app_mode == t("nav_arena"):
        st.header(t("settings"))

        # API klíče – nové pořadí: Gemini, Mistral, NVIDIA
        st.session_state.gemini_key = st.text_input(f"🔑 Gemini {t('api_keys')}:", type="password", value=st.session_state.gemini_key, placeholder="AIzaSy...")
        st.session_state.mistral_key = st.text_input(f"🔑 Mistral {t('api_keys')}:", type="password", value=st.session_state.mistral_key, placeholder="...")
        st.session_state.nim_key = st.text_input(f"🔑 NVIDIA {t('api_keys')}:", type="password", value=st.session_state.nim_key, placeholder="nvapi-...")

        if st.button(t("save_keys"), use_container_width=True):
            g = st.session_state.gemini_key.replace("'", "\\'")
            n = st.session_state.nim_key.replace("'", "\\'")
            m = st.session_state.mistral_key.replace("'", "\\'")
            js = f"<script>localStorage.setItem('arena_gemini', '{g}');localStorage.setItem('arena_nim', '{n}');localStorage.setItem('arena_mistral', '{m}');</script>"
            components.html(js, height=0)
            st.success(t("save_keys_success"))

        # Dostupné providery – nové pořadí: Gemini, Mistral, NVIDIA NIM
        available_providers = []
        if st.session_state.gemini_key.strip(): available_providers.append("Gemini")
        if st.session_state.mistral_key.strip(): available_providers.append("Mistral")
        if st.session_state.nim_key.strip(): available_providers.append("NVIDIA NIM")
        select_options = available_providers if available_providers else ["(Enter at least one key)"]

        if st.session_state.provider_a not in select_options: st.session_state.provider_a = select_options[0]
        if st.session_state.provider_b not in select_options: st.session_state.provider_b = select_options[0]
        if st.session_state.provider_mod not in select_options: st.session_state.provider_mod = select_options[0]

        st.divider()

        # --- PRESET ---
        st.selectbox(
            t("preset_label"),
            options=PRESET_KEYS,
            format_func=lambda k: t(f"preset_{k}"),
            key="preset_select",
            on_change=apply_preset_callback,
            help=t("preset_help"),
        )

        st.divider()
        st.session_state.max_rounds = st.slider(t("rounds"), min_value=2, max_value=30, value=st.session_state.max_rounds)

        # --- OSOBNOST A ---
        st.subheader(t("persona_a"))
        st.session_state.role_a_name = st.text_input(f"{t('name')} A", value=st.session_state.role_a_name)
        st.session_state.provider_a = st.selectbox(f"{t('provider_select')} A:", select_options, index=select_options.index(st.session_state.provider_a) if st.session_state.provider_a in select_options else 0)

        col_t, col_e = st.columns(2)
        with col_t:
            st.selectbox(t("temperament_label"), options=TEMPERAMENT_KEYS, format_func=lambda k: t(f"temperament_{k}"), key="temperament_a")
        with col_e:
            st.selectbox(t("expertise_label"), options=EXPERTISE_KEYS, format_func=lambda k: t(f"expertise_{k}"), key="expertise_a")
        st.button(t("random_button"), key="random_a", on_click=randomize_persona_a, use_container_width=True)

        input_a_opts = ["manual", "upload"]
        input_a_idx = 0 if st.session_state.get("input_type_a", "manual") in ["manual", "Ručně"] else 1
        st.session_state.input_type_a = st.radio(
            f"{t('input_type')} A:",
            options=input_a_opts,
            format_func=lambda x: t(x),
            index=input_a_idx
        )
        if st.session_state.input_type_a == "manual":
            st.session_state.role_a_prompt = st.text_area(f"{t('instructions')} A", value=st.session_state.role_a_prompt)
        else:
            file_a = st.file_uploader(f"{t('upload')} A (PDF, MD, TXT)", type=["pdf", "md", "txt"], key="file_a")
            if file_a: st.session_state.role_a_prompt = extract_text_from_file(file_a)

        # --- OSOBNOST B ---
        st.subheader(t("persona_b"))
        st.session_state.role_b_name = st.text_input(f"{t('name')} B", value=st.session_state.role_b_name)
        st.session_state.provider_b = st.selectbox(f"{t('provider_select')} B:", select_options, index=select_options.index(st.session_state.provider_b) if st.session_state.provider_b in select_options else 0)

        col_t2, col_e2 = st.columns(2)
        with col_t2:
            st.selectbox(t("temperament_label"), options=TEMPERAMENT_KEYS, format_func=lambda k: t(f"temperament_{k}"), key="temperament_b")
        with col_e2:
            st.selectbox(t("expertise_label"), options=EXPERTISE_KEYS, format_func=lambda k: t(f"expertise_{k}"), key="expertise_b")
        st.button(t("random_button"), key="random_b", on_click=randomize_persona_b, use_container_width=True)

        input_b_opts = ["manual", "upload"]
        input_b_idx = 0 if st.session_state.get("input_type_b", "manual") in ["manual", "Ručně"] else 1
        st.session_state.input_type_b = st.radio(
            f"{t('input_type')} B:",
            options=input_b_opts,
            format_func=lambda x: t(x),
            index=input_b_idx
        )
        if st.session_state.input_type_b == "manual":
            st.session_state.role_b_prompt = st.text_area(f"{t('instructions')} B", value=st.session_state.role_b_prompt)
        else:
            file_b = st.file_uploader(f"{t('upload')} B (PDF, MD, TXT)", type=["pdf", "md", "txt"], key="file_b")
            if file_b: st.session_state.role_b_prompt = extract_text_from_file(file_b)

        # --- ROZHODČÍ ---
        st.subheader(t("moderator"))
        st.session_state.provider_mod = st.selectbox(f"{t('provider_select')}:", select_options, index=select_options.index(st.session_state.provider_mod) if st.session_state.provider_mod in select_options else 0)

        # --- SPOLEČNÁ PRAVIDLA ---
        st.divider()
        st.selectbox(t("response_length_label"), options=LENGTH_KEYS, format_func=lambda k: t(f"length_{k}"), key="response_length")
        st.radio(t("debate_goal_label"), options=GOAL_KEYS, format_func=lambda k: t(f"goal_{k}"), key="debate_goal")
        st.multiselect(t("rules_label"), options=RULE_KEYS, format_func=lambda k: t(f"rule_{k}"), key="debate_rules")

        # --- POKROČILÉ ---
        with st.expander(t("advanced_settings")):
            st.session_state.memory_limit = st.slider(t("memory_limit_label"), min_value=2, max_value=30, value=st.session_state.memory_limit)

    st.divider()
    st.caption("© 2026 Lukáš Buchvald")

# --- 4. OBSAH JEDNOTLIVÝCH SEKCI ---

if app_mode == t("nav_help"):
    st.title(t("h_title"))

    st.markdown(f"## {t('h_sub')}")
    st.markdown(f"1. {t('h_p1')}")
    st.markdown(f"2. {t('h_p2')}")
    st.markdown(f"3. {t('h_p3')}")

    st.divider()
    st.markdown(t("h_start"))
    st.markdown(t("h_start_gemini"))
    st.markdown(t("h_start_other"))
    st.markdown(t("h_start_save"))

    with st.expander(t("exp_gemini")):
        st.markdown("""
        **How to get the key:**
        1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
        2. Sign in with your Google account.
        3. Click on **Create API key**.
        4. Copy the generated key (starts with `AIza...`) and paste it into the sidebar.

        **Limits (Free tier):** Completely free. ~15 requests per minute, daily limit 500 - 1500 requests.
        """)

    with st.expander(t("exp_mistral")):
        st.markdown("""
        **How to get the key:**
        1. Go to [Mistral Console](https://console.mistral.ai/).
        2. Register.
        3. Go to **API Keys** -> **Create new key**.
        """)

    with st.expander(t("exp_nvidia")):
        st.markdown("""
        **How to get the key:**
        1. Go to [NVIDIA Build](https://build.nvidia.com/).
        2. Register.
        3. Click on your name in the top right -> **API Keys**.
        4. Generate a new key (starts with `nvapi-...`).

        **Limits (Free tier):** Generous limits (~40 requests per minute), great for long texts.
        """)

    with st.expander(t("exp_crit")):
        st.markdown("""
        After the debate ends, you can have the debate and the judge's verdict evaluated by another AI:

        *   **Direct API:** If you have a key in the app, the critique will be generated directly by the server and saved to R2.
        *   **External chat:** If you want to use a better model (e.g., paid ChatGPT Plus or Claude), download the debate PDF, open the chat link, and paste the prepared prompt. Then copy the result back into the app.
        """)

elif app_mode == t("nav_arena"):
    st.title(t("debate_title"))

    if not available_providers:
        st.warning(t("no_key_error"))
    else:
        st.info(t("tip"))

    st.caption(t("debate_caption"))

    # --- ZADÁNÍ TÉMATU ---
    topic_opts = ["manual", "upload"]
    topic_idx = 0 if st.session_state.get("topic_input_type", "manual") in ["manual", "Ručně"] else 1
    st.session_state.topic_input_type = st.radio(
        t("topic_type"),
        options=topic_opts,
        format_func=lambda x: t(x),
        index=topic_idx
    )

    if st.session_state.topic_input_type == "manual":
        st.session_state.topic_input = st.text_input(t("topic_text"), value=st.session_state.topic_input, placeholder="...")
        topic = st.session_state.topic_input
        st.session_state.topic_document_text = ""
        st.session_state.uploaded_files_hash = ""
    else:
        st.session_state.topic_input = st.text_input(t("topic_file"), value=st.session_state.topic_input, placeholder="...")
        topic = st.session_state.topic_input
        topic_files = st.file_uploader(t("upload_topic"), type=["pdf", "md", "txt"], accept_multiple_files=True)

        if topic_files:
            file_names = "_".join([f.name for f in topic_files])
            if st.session_state.uploaded_files_hash != file_names:
                with st.spinner("Loading..."):
                    full_text = ""
                    for f in topic_files:
                        full_text += f"--- Document: {f.name} ---\n" + extract_text_from_file(f) + "\n\n"
                    st.session_state.topic_document_text = full_text
                    st.session_state.uploaded_files_hash = file_names
                    st.success(f"✅ Successfully loaded {len(topic_files)} documents.")

    if st.button(t("start_debate"), type="primary"):
        if not available_providers:
            st.error(t("no_key_error"))
            st.stop()
        if not topic.strip() or not st.session_state.role_a_name.strip() or not st.session_state.role_a_prompt.strip() or not st.session_state.role_b_name.strip() or not st.session_state.role_b_prompt.strip():
            st.error("Please fill in the topic and settings for both personas!")
            st.stop()
        if st.session_state.topic_input_type == "upload" and not st.session_state.topic_document_text:
            st.error("Please upload at least one document!")
            st.stop()

        st.session_state.full_history = []
        st.session_state.current_topic = topic
        st.session_state.debate_active = False
        st.session_state.md_content = ""
        st.session_state.pdf_bytes = b""
        st.session_state.file_base_name = "debata"
        st.session_state.topic_summary = ""
        reset_critique_state()

        # --- SESTAVENÍ ROZŠÍŘENÝCH PROMPTŮ ---
        lang = st.session_state.lang
        enhanced_prompt_a = enhance_role_prompt(
            st.session_state.role_a_prompt,
            st.session_state.temperament_a,
            st.session_state.expertise_a,
            st.session_state.response_length,
            st.session_state.debate_rules,
            lang,
        )
        enhanced_prompt_b = enhance_role_prompt(
            st.session_state.role_b_prompt,
            st.session_state.temperament_b,
            st.session_state.expertise_b,
            st.session_state.response_length,
            st.session_state.debate_rules,
            lang,
        )

        try:
            gemini_client = genai.Client(api_key=st.session_state.gemini_key.strip(), http_options=types.HttpOptions(timeout=180000)) if "Gemini" in available_providers else None
            mistral_client = OpenAI(api_key=st.session_state.mistral_key.strip(), base_url="https://api.mistral.ai/v1", timeout=180.0) if "Mistral" in available_providers else None
            nim_client = OpenAI(api_key=st.session_state.nim_key.strip(), base_url="https://integrate.api.nvidia.com/v1", timeout=180.0) if "NVIDIA NIM" in available_providers else None
        except Exception as e:
            st.error(f"Client initialization error: {e}")
            st.stop()

        with st.spinner("Checking available models..."):
            gemini_models = get_available_gemini_models(gemini_client) if gemini_client else []
            mistral_models = get_available_mistral_models(mistral_client) if mistral_client else []
            nvidia_models = NVIDIA_PREFERRED if nim_client else []

        model_info = []
        if gemini_models: model_info.append(f"Gemini: `{', '.join(gemini_models)}`")
        if mistral_models: model_info.append(f"Mistral: `{', '.join(mistral_models)}`")
        if nvidia_models: model_info.append(f"NVIDIA: `{', '.join(nvidia_models)}`")
        st.info("Used models: " + " | ".join(model_info))

        st.divider()
        st.markdown(f"### 📌 Topic: *{topic}*")

        chat_container = st.container()
        progress_bar = st.progress(0)
        memory_limit = st.session_state.memory_limit

        def call_ai(system_prompt, user_prompt, provider):
            full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
            if provider == "Gemini":
                for model_name in gemini_models:
                    for attempt in range(2):
                        try:
                            response = gemini_client.models.generate_content(model=model_name, contents=full_prompt, config=types.GenerateContentConfig())
                            if response.text and response.text.strip(): return response.text, model_name
                        except Exception as e:
                            if getattr(e, 'code', None) in [503, 429] and attempt == 0: time.sleep(2)
                            else: break
                raise Exception("All Gemini models failed.")

            elif provider == "Mistral":
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                for model_name in mistral_models:
                    for attempt in range(2):
                        try:
                            response = mistral_client.chat.completions.create(model=model_name, messages=messages, temperature=0.7)
                            if response.choices[0].message.content: return response.choices[0].message.content, model_name
                        except Exception:
                            if attempt == 0: time.sleep(2)
                            else: break
                raise Exception("All Mistral models failed.")

            elif provider == "NVIDIA NIM":
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                for model_name in nvidia_models:
                    for attempt in range(2):
                        try:
                            response = nim_client.chat.completions.create(model=model_name, messages=messages, temperature=0.7, extra_body={"chat_template_kwargs":{"enable_thinking":True}})
                            if response.choices[0].message.content: return response.choices[0].message.content, model_name
                        except Exception:
                            if attempt == 0: time.sleep(2)
                            else: break
                raise Exception("All NVIDIA models failed.")

        # --- GENEROVÁNÍ SOUHRNU DOKUMENTŮ ---
        if st.session_state.topic_input_type == "upload" and st.session_state.topic_document_text:
            with st.spinner("Analyzing documents and preparing a summary..."):
                summary_prompt = "Jsi expert na analýzu dokumentů. Z následujících textů vytvoř strukturovaný souhrn. Uveď hlavní teze, klíčová fakta a přímé citace, které by měly být použity v diskuzi." if lang == "cs" else "You are a document analysis expert. Create a structured summary from the following texts. State the main theses, key facts, and direct quotes that should be used in the debate."
                try:
                    priority = [p for p in ["Gemini", "Mistral", "NVIDIA NIM"] if p in available_providers]
                    summary_text = None
                    for p in priority:
                        try:
                            summary_text, _ = call_ai(summary_prompt, st.session_state.topic_document_text, p)
                            break
                        except Exception: continue
                    st.session_state.topic_summary = summary_text or "Failed to generate document summary."
                except Exception as e:
                    st.session_state.topic_summary = f"Failed to generate document summary: {e}"

            st.markdown("#### 📄 Initial document summary")
            st.info(st.session_state.topic_summary)
            st.divider()

        debate_context_intro = f"Topic: '{topic}'.\n\n"
        if st.session_state.topic_summary:
            debate_context_intro += f"Here is the summary of the source documents:\n{st.session_state.topic_summary}\n\n"

        # ZAHÁJENÍ DISKUZE (používá enhanced_prompt_a/b)
        with chat_container.chat_message("user", avatar="🔵"):
            st.markdown(f"**{st.session_state.role_a_name}:**")
            with st.spinner("Starting debate..."):
                resp_a, mod_a = call_ai(enhanced_prompt_a, debate_context_intro + ("Zahaj diskuzi a předlož svůj první argument." if lang == "cs" else "Start the debate and present your first argument."), st.session_state.provider_a)
            st.markdown(resp_a)
            st.caption(f"🤖 `{mod_a}`")
        st.session_state.full_history.append((st.session_state.role_a_name, resp_a, mod_a))

        # SMYČKA DEBATY
        for r in range(st.session_state.max_rounds):
            progress_bar.progress((r + 1) / st.session_state.max_rounds)
            time.sleep(get_delay_for_provider(st.session_state.provider_b))

            context_b = debate_context_intro + "Context:\n" + "\n".join([f"{s}: {t}" for s, t, m in st.session_state.full_history[-memory_limit:]]) + (f"\nNow it's your turn ({st.session_state.role_b_name}). React to your opponent's arguments." if lang == "en" else f"\nNyní jsi na řadě ty ({st.session_state.role_b_name}). Reaguj na argumenty oponenta.")
            with chat_container.chat_message("assistant", avatar="🔴"):
                st.markdown(f"**{st.session_state.role_b_name}:**")
                with st.spinner("Reacting..."):
                    resp_b, mod_b = call_ai(enhanced_prompt_b, context_b, st.session_state.provider_b)
                st.markdown(resp_b)
                st.caption(f"🤖 `{mod_b}`")
            st.session_state.full_history.append((st.session_state.role_b_name, resp_b, mod_b))

            if r < st.session_state.max_rounds - 1:
                time.sleep(get_delay_for_provider(st.session_state.provider