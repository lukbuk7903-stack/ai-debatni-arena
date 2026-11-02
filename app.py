import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import errors, types
import time, random
from datetime import datetime
import pypdf
import os
import urllib.request
import markdown
from weasyprint import HTML, CSS
from openai import OpenAI, APITimeoutError
import base64

st.set_page_config(page_title="AI Debatní Aréna", layout="wide")

# --- 1. INICIALIZACE PAMĚTI (Session State) ---
if "debate_active" not in st.session_state:
    st.session_state.debate_active = False
if "full_history" not in st.session_state:
    st.session_state.full_history = []
if "final_summary" not in st.session_state:
    st.session_state.final_summary = ""
if "model_mod_used" not in st.session_state:
    st.session_state.model_mod_used = ""
if "current_topic" not in st.session_state:
    st.session_state.current_topic = ""

if "md_content" not in st.session_state:
    st.session_state.md_content = ""
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = b""

form_defaults = {
    "gemini_key": "", "nim_key": "", "mistral_key": "",
    "role_a_name": "", "role_a_prompt": "", "provider_a": "Gemini", "input_type_a": "Ručně",
    "role_b_name": "", "role_b_prompt": "", "provider_b": "Gemini", "input_type_b": "Ručně",
    "provider_mod": "Gemini", "topic_input": "", "max_rounds": 4
}
for key, default in form_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- 2. POMOCNÉ FUNKCE ---
def extract_text_from_file(uploaded_file):
    if uploaded_file is None:
        return ""
    file_extension = uploaded_file.name.split('.')[-1].lower()
    try:
        if file_extension == 'pdf':
            pdf_reader = pypdf.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                if page.extract_text():
                    text += page.extract_text() + "\n"
            return text.strip()
        else:
            return uploaded_file.read().decode("utf-8").strip()
    except Exception as e:
        st.error(f"Chyba při čtení souboru {uploaded_file.name}: {e}")
        return ""

def generate_pdf(text_content):
    html_body = markdown.markdown(text_content, extensions=['tables', 'nl2br'])
    css_style = """
    @page { size: A4; margin: 2cm; @bottom-center { content: "Strana " counter(page) " z " counter(pages); font-size: 9pt; color: #666; } }
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
        st.error(f"Chyba při generování PDF: {e}")
        return b""

GEMINI_PREFERRED = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash"]
NVIDIA_PREFERRED = ["nvidia/nemotron-3-ultra-550b-a55b"]
MISTRAL_PREFERRED = ["ministral-3b-2512", "ministral-8b-2512", "codestral-2508", "mistral-large-2512"]

def get_available_gemini_models(client):
    try:
        models = client.models.list()
        available = [m.name.replace('models/', '') for m in models if 'generateContent' in getattr(m, 'supported_generation_methods', [])]
        if not available: return GEMINI_PREFERRED
        verified = [m for m in GEMINI_PREFERRED if m in available]
        return verified if verified else available
    except Exception as e:
        st.warning(f"⚠️ Nepodařilo se načíst seznam modelů Gemini: {e}")
        return GEMINI_PREFERRED

def get_available_nvidia_models(client):
    return NVIDIA_PREFERRED

def get_available_mistral_models(client):
    try:
        all_models = client.models.list()
        available_ids = [m.id for m in all_models.data if m.id]
        if not available_ids: return MISTRAL_PREFERRED
        verified = [m for m in MISTRAL_PREFERRED if m in available_ids]
        return verified if verified else available_ids[:3]
    except Exception as e:
        st.warning(f"⚠️ Nepodařilo se načíst seznam modelů Mistral: {e}")
        return MISTRAL_PREFERRED

def get_delay_for_provider(provider):
    if provider == "NVIDIA NIM": return 2.0
    elif provider == "Gemini": return 6.0
    elif provider == "Mistral": return 3.0
    return 2.0

def render_downloads():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    md_b64 = base64.b64encode(st.session_state.md_content.encode('utf-8')).decode('utf-8')
    pdf_b64 = base64.b64encode(st.session_state.pdf_bytes).decode('utf-8') if st.session_state.pdf_bytes else ""
    
    md_href = f"data:application/octet-stream;base64,{md_b64}"
    pdf_href = f"data:application/pdf;base64,{pdf_b64}"
    
    html_code = f"""
    <div style="display: flex; gap: 10px; font-family: 'Source Sans Pro', sans-serif;">
        <a href="{md_href}" download="diskuze_{timestamp}.md" 
           style="flex: 1; text-align: center; padding: 10px; background-color: #f0f2f6; color: #31333f; text-decoration: none; border-radius: 5px; border: 1px solid #d6d6d6; font-size: 16px;">
           📥 Stáhnout jako Markdown (.md)
        </a>
        <a href="{pdf_href}" download="diskuze_{timestamp}.pdf" 
           style="flex: 1; text-align: center; padding: 10px; background-color: #ff4b4b; color: white; text-decoration: none; border-radius: 5px; font-size: 16px;">
           📄 Stáhnout jako PDF (.pdf)
        </a>
    </div>
    """
    components.html(html_code, height=60)

# Načtení klíčů ze Secrets (pokud jsou nastaveny)
try:
    secret_gemini = st.secrets["GEMINI_API_KEY"]
except:
    secret_gemini = ""
try:
    secret_nim = st.secrets["NVIDIA_NIM_API_KEY"]
except:
    secret_nim = ""
try:
    secret_mistral = st.secrets["MISTRAL_API_KEY"]
except:
    secret_mistral = ""
    
# --- 3. POSTRANNÍ PANEL ---
with st.sidebar:
    st.header("🧭 Navigace")
    app_mode = st.radio("Vyberte sekci:", ["⚔️ Debatní Aréna", "❓ Nápověda a návody"], index=0)
    st.divider()

    if app_mode == "⚔️ Debatní Aréna":
        st.header("⚙️ Nastavení debaty")
        
        st.session_state.gemini_key = st.text_input("🔑 Gemini API klíč:", type="password", value=st.session_state.gemini_key or secret_gemini, placeholder="Nepovinné (AIzaSy...)")
        st.session_state.nim_key = st.text_input("🔑 NVIDIA NIM API klíč:", type="password", value=st.session_state.nim_key or secret_nim, placeholder="Nepovinné (nvapi-...)")
        st.session_state.mistral_key = st.text_input("🔑 Mistral API klíč:", type="password", value=st.session_state.mistral_key or secret_mistral, placeholder="Nepovinné (...)")
        
        available_providers = []
        if st.session_state.gemini_key.strip(): available_providers.append("Gemini")
        if st.session_state.nim_key.strip(): available_providers.append("NVIDIA NIM")
        if st.session_state.mistral_key.strip(): available_providers.append("Mistral")
        
        select_options = available_providers if available_providers else ["(Zadejte alespoň jeden klíč)"]
        
        if st.session_state.provider_a not in select_options: st.session_state.provider_a = select_options[0]
        if st.session_state.provider_b not in select_options: st.session_state.provider_b = select_options[0]
        if st.session_state.provider_mod not in select_options: st.session_state.provider_mod = select_options[0]

        st.divider()
        st.session_state.max_rounds = st.slider("Počet výměn názorů (kol)", min_value=2, max_value=30, value=st.session_state.max_rounds)
        memory_limit = 10

        st.subheader("Osobnost A")
        st.session_state.role_a_name = st.text_input("Jméno A", value=st.session_state.role_a_name, placeholder="Zde napiš mluvčího...")
        st.session_state.provider_a = st.selectbox("Poskytovatel A:", select_options, index=select_options.index(st.session_state.provider_a) if st.session_state.provider_a in select_options else 0)
        st.session_state.input_type_a = st.radio("Způsob zadání instrukcí pro A:", ["Ručně", "Nahrát soubor"], index=0 if st.session_state.input_type_a == "Ručně" else 1)
        
        if st.session_state.input_type_a == "Ručně":
            st.session_state.role_a_prompt = st.text_area("Instrukce pro A", value=st.session_state.role_a_prompt, placeholder="Zde napiš, jak se má mluvčí chovat...")
        else:
            file_a = st.file_uploader("Nahrajte charakteristiku A (PDF, MD, TXT)", type=["pdf", "md", "txt"], key="file_a")
            if file_a: st.session_state.role_a_prompt = extract_text_from_file(file_a)

        st.subheader("Osobnost B")
        st.session_state.role_b_name = st.text_input("Jméno B", value=st.session_state.role_b_name, placeholder="Zde napiš mluvčího...")
        st.session_state.provider_b = st.selectbox("Poskytovatel B:", select_options, index=select_options.index(st.session_state.provider_b) if st.session_state.provider_b in select_options else 0)
        st.session_state.input_type_b = st.radio("Způsob zadání instrukcí pro B:", ["Ručně", "Nahrát soubor"], index=0 if st.session_state.input_type_b == "Ručně" else 1)
        
        if st.session_state.input_type_b == "Ručně":
            st.session_state.role_b_prompt = st.text_area("Instrukce pro B", value=st.session_state.role_b_prompt, placeholder="Zde napiš, jak se má mluvčí chovat...")
        else:
            file_b = st.file_uploader("Nahrajte charakteristiku B (PDF, MD, TXT)", type=["pdf", "md", "txt"], key="file_b")
            if file_b: st.session_state.role_b_prompt = extract_text_from_file(file_b)

        st.subheader("Moderátor (Rozhodčí)")
        st.session_state.provider_mod = st.selectbox("Poskytovatel moderátora:", select_options, index=select_options.index(st.session_state.provider_mod) if st.session_state.provider_mod in select_options else 0)

# --- 4. OBSAH JEDNOTLIVÝCH SEKCI ---

if app_mode == "❓ Nápověda a návody":
    st.title("📖 Nápověda a návody")
    st.markdown("""... (Zde je text nápovědy) ...""") # Zkráceno pro přehlednost

elif app_mode == "⚔️ Debatní Aréna":
    st.title("🗣️ AI Debatní Aréna")
    st.caption("Automatizovaná diskuze dvou AI osobností s dynamickým výběrem modelů.")
    
    st.session_state.topic_input = st.text_input("Téma diskuze:", value=st.session_state.topic_input, placeholder="Zadej o čem mají diskutovat...")
    topic = st.session_state.topic_input

    if st.button("🚀 Spustit diskuzi", type="primary"):
        if not available_providers:
            st.error("⚠️ Pro spuštění diskuze musíte nejprve zadat alespoň jeden API klíč!")
            st.stop()
        if not topic.strip() or not st.session_state.role_a_name.strip() or not st.session_state.role_a_prompt.strip() or not st.session_state.role_b_name.strip() or not st.session_state.role_b_prompt.strip():
            st.error("⚠️ Pro spuštění diskuze musíte vyplnit téma a nastavení pro obě osobnosti!")
            st.stop()
        
        st.session_state.full_history = []
        st.session_state.current_topic = topic
        st.session_state.debate_active = False 
        st.session_state.md_content = ""
        st.session_state.pdf_bytes = b""
        
        try:
            gemini_client = genai.Client(api_key=st.session_state.gemini_key.strip(), http_options=types.HttpOptions(timeout=180000)) if "Gemini" in available_providers else None
            nim_client = OpenAI(api_key=st.session_state.nim_key.strip(), base_url="https://integrate.api.nvidia.com/v1", timeout=180.0) if "NVIDIA NIM" in available_providers else None
            mistral_client = OpenAI(api_key=st.session_state.mistral_key.strip(), base_url="https://api.mistral.ai/v1", timeout=180.0) if "Mistral" in available_providers else None
        except Exception as e:
            st.error(f"Chyba při inicializaci klienta: {e}")
            st.stop()

        with st.spinner("Zjišťuji aktuálně dostupné modely..."):
            gemini_models = get_available_gemini_models(gemini_client) if gemini_client else []
            nvidia_models = get_available_nvidia_models(nim_client) if nim_client else []
            mistral_models = get_available_mistral_models(mistral_client) if mistral_client else []
        
        model_info = []
        if gemini_models: model_info.append(f"Gemini: `{', '.join(gemini_models)}`")
        if nvidia_models: model_info.append(f"NVIDIA: `{', '.join(nvidia_models)}`")
        if mistral_models: model_info.append(f"Mistral: `{', '.join(mistral_models)}`")
        st.info("Použité modely: " + " | ".join(model_info))

        st.divider()
        st.markdown(f"### 📌 Téma: *{topic}*")
        
        chat_container = st.container()
        progress_bar = st.progress(0)

        def call_ai(system_prompt, user_prompt, provider):
            full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
            if provider == "Gemini":
                config = types.GenerateContentConfig()
                last_error = None
                for model_name in gemini_models:
                    for attempt in range(2):
                        try:
                            response = gemini_client.models.generate_content(model=model_name, contents=full_prompt, config=config)
                            return response.text, model_name
                        except Exception as e:
                            last_error = e
                            if getattr(e, 'code', None) in [503, 429] and attempt == 0: time.sleep(2)
                            else: break
                raise Exception(f"Všechny Gemini modely selhaly: {last_error}")
                
            elif provider == "NVIDIA NIM":
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                last_error = None
                for model_name in nvidia_models:
                    for attempt in range(2):
                        try:
                            response = nim_client.chat.completions.create(model=model_name, messages=messages, temperature=0.7, extra_body={"chat_template_kwargs":{"enable_thinking":True}})
                            return response.choices[0].message.content, model_name
                        except Exception as e:
                            last_error = e
                            if attempt == 0: time.sleep(2)
                            else: break
                raise Exception(f"Všechny NVIDIA modely selhaly: {last_error}")
                
            elif provider == "Mistral":
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                last_error = None
                for model_name in mistral_models:
                    for attempt in range(2):
                        try:
                            response = mistral_client.chat.completions.create(model=model_name, messages=messages, temperature=0.7)
                            return response.choices[0].message.content, model_name
                        except Exception as e:
                            last_error = e
                            if attempt == 0: time.sleep(2)
                            else: break
                raise Exception(f"Všechny Mistral modely selhaly: {last_error}")

        # 1. Úvodní slovo Osobnosti A
        with chat_container.chat_message("user", avatar="🔵"):
            st.markdown(f"**{st.session_state.role_a_name}:**")
            with st.spinner("Zahajuje diskuzi..."):
                resp_a, mod_a = call_ai(st.session_state.role_a_prompt, f"Zahaj diskuzi na téma: '{topic}'. Vycházej ze svých znalostí a předlož svůj první argument.", st.session_state.provider_a)
            st.markdown(resp_a)
            st.caption(f"🤖 `{mod_a}`")
        
        st.session_state.full_history.append((st.session_state.role_a_name, resp_a, mod_a))

        # 2. Smyčka debaty
        for r in range(st.session_state.max_rounds):
            progress_bar.progress((r + 1) / st.session_state.max_rounds)
            time.sleep(get_delay_for_provider(st.session_state.provider_b))
            
            # Tah Osobnosti B
            context_b = "Kontext diskuze:\n" + "\n".join([f"{s}: {t}" for s, t, m in st.session_state.full_history[-memory_limit:]]) + f"\nNyní jsi na řadě ty ({st.session_state.role_b_name}). Reaguj na argumenty oponenta."
            
            with chat_container.chat_message("assistant", avatar="🔴"):
                st.markdown(f"**{st.session_state.role_b_name}:**")
                with st.spinner("Reaguje..."):
                    resp_b, mod_b = call_ai(st.session_state.role_b_prompt, context_b, st.session_state.provider_b)
                st.markdown(resp_b)
                st.caption(f"🤖 `{mod_b}`")
            st.session_state.full_history.append((st.session_state.role_b_name, resp_b, mod_b))

            # Tah Osobnosti A (pouze pokud to není poslední kolo)
            if r < st.session_state.max_rounds - 1:
                time.sleep(get_delay_for_provider(st.session_state.provider_a))
                context_a = "Kontext diskuze:\n" + "\n".join([f"{s}: {t}" for s, t, m in st.session_state.full_history[-memory_limit:]]) + f"\nNyní jsi na řadě ty ({st.session_state.role_a_name}). Reaguj na argumenty oponenta."
                
                with chat_container.chat_message("user", avatar="🔵"):
                    st.markdown(f"**{st.session_state.role_a_name}:**")
                    with st.spinner("Reaguje..."):
                        resp_a, mod_a = call_ai(st.session_state.role_a_prompt, context_a, st.session_state.provider_a)
                    st.markdown(resp_a)
                    st.caption(f"🤖 `{mod_a}`")
                st.session_state.full_history.append((st.session_state.role_a_name, resp_a, mod_a))

        progress_bar.progress(1.0)
        time.sleep(get_delay_for_provider(st.session_state.provider_mod))

        # Vykreslení rozhodčího POUZE JEDNOU
        with chat_container.chat_message("assistant", avatar="⚖️"):
            st.markdown("**Rozhodčí:**")
            with st.spinner("Vyhodnocuje argumenty..."):
                summary_context = "Průběh debaty:\n" + "\n".join([f"{s}: {t}" for s, t, m in st.session_state.full_history])
                final_sum, mod_mod = call_ai("Jsi přísný rozhodčí. Zhodnoť argumenty. Urči vítěze a vysvětli proč.", summary_context, st.session_state.provider_mod)
            st.markdown(final_sum)
            st.caption(f"🤖 `{mod_mod}`")
            
        st.session_state.final_summary = final_sum
        st.session_state.model_mod_used = mod_mod
        st.session_state.debate_active = True
        
        # Příprava souborů (s přidáním hlavičky pro rozhodčího v Markdownu)
        with st.spinner("Připravuji soubory ke stažení..."):
            md_history = ""
            for sender, text, model in st.session_state.full_history:
                md_history += f"### {sender}\n{text}\n\n<small>Použitý model: {model}</small>\n\n---\n\n"
            
            st.session_state.md_content = f"# Diskuze: {st.session_state.current_topic}\n\n**Datum:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n" + md_history + f"### Rozhodčí\n{final_sum}\n\n<small>Použitý model: {mod_mod}</small>"
            st.session_state.pdf_bytes = generate_pdf(st.session_state.md_content)
        
        st.divider()
        # Tady už NENÍ st.subheader a st.info, aby se to nezdvojovalo
        render_downloads()
        
        st.divider()
        if st.button("🔄 Nová debata", use_container_width=True):
            st.session_state.debate_active = False
            st.session_state.full_history = []
            st.session_state.final_summary = ""
            st.session_state.md_content = ""
            st.session_state.pdf_bytes = b""
            st.rerun()
            
        st.stop()

    if st.session_state.debate_active:
        st.divider()
        st.markdown(f"### 📌 Téma: *{st.session_state.current_topic}*")
        
        for i, (sender, text, model_used) in enumerate(st.session_state.full_history):
            avatar = "🔵" if i % 2 == 0 else "🔴"
            role = "user" if i % 2 == 0 else "assistant"
            with st.chat_message(role, avatar=avatar):
                st.markdown(f"**{sender}:**\n\n{text}")
                st.caption(f"🤖 `{model_used}`")

        # Vykreslení rozhodčího i při obnovení stránky
        with st.chat_message("assistant", avatar="⚖️"):
            st.markdown("**Rozhodčí:**")
            st.markdown(st.session_state.final_summary)
            st.caption(f"🤖 `{st.session_state.model_mod_used}`")

        st.divider()
        render_downloads()
                
        st.divider()
        if st.button("🔄 Nová debata", use_container_width=True):
            st.session_state.debate_active = False
            st.session_state.full_history = []
            st.session_state.final_summary = ""
            st.session_state.md_content = ""
            st.session_state.pdf_bytes = b""
            st.rerun()
