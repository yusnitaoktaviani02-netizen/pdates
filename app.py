import os
import re
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Pusat Informasi Masjid Syuhada",
    page_icon="🕌",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH = Path(__file__).parent / "Metadata_DCMA_RAG_Masjid_Syuhada_101.xlsx"

st.markdown("""
<style>
.block-container {max-width: 1100px; padding-top: 2rem; padding-bottom: 3rem;}
.hero {padding: 1.35rem 1.5rem; border-radius: 16px; background: linear-gradient(120deg,#123b35,#28665a); color:white; margin-bottom:1rem;}
.hero h1 {color:white; margin:0 0 .35rem 0;}
.hero p {color:#e8f3ee; margin:0;}
.source-card {border:1px solid rgba(128,128,128,.35); border-radius:12px; padding: .9rem 1rem; margin:.5rem 0;}
.small-muted {font-size:.86rem; opacity:.75;}
</style>
<div class="hero">
<h1>🕌 Pusat Informasi Masjid Syuhada</h1>
<p>Chatbot publik berbasis dokumen untuk menelusuri metadata, elemen arsitektur, catatan kerusakan, dan panduan pelestarian.</p>
</div>
""", unsafe_allow_html=True)

SHEET_CONFIG = {
    "Metadata_Dublin_Core": ("Dokumen sumber", "source_document"),
    "Elemen_Arsitektur": ("Elemen arsitektur", "architectural_element"),
    "Inventarisasi_Kerusakan": ("Inventarisasi kerusakan", "damage"),
    "Panduan_Pelestarian": ("Panduan pelestarian", "conservation_policy"),
    "Chunk_RAG": ("Chunk RAG", "rag_chunk"),
}

def clean(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    return "" if value.lower() in {"nan", "none", "nat"} else value

def row_to_text(sheet, row):
    # Build a compact, field-labelled passage while preserving source traceability.
    priority = {
        "Metadata_Dublin_Core": ["record_id","dc:title","dc:creator","dc:subject","dc:description","dc:publisher","dc:date","dc:identifier","dc:source","dc:coverage","evidence_note","source_filename","pdf_pages","doc_url"],
        "Elemen_Arsitektur": ["element_id","dc:title","element_type","element_code","building_mass","room_location_code","location_text","material","finish","form_description","quantity","significance_label","condition_summary","dc:description","dc:subject","dc:source","source_id","source_page_pdf","evidence_text","verification_status","rag_keywords","doc_url"],
        "Inventarisasi_Kerusakan": ["damage_id","dc:title","element_category","damage_code_source","building_mass","room_or_location_code","damage_type","damage_description","suspected_cause_source","severity","recommended_action","dc:source","source_id","source_page_pdf","evidence_text","verification_status","rag_keywords","doc_url"],
        "Panduan_Pelestarian": ["policy_id","dc:title","priority_source","element_or_scope","recommendation_source_text","interpretation_note","dc:source","source_id","source_page_pdf","evidence_text","rag_keywords","doc_url"],
        "Chunk_RAG": ["chunk_id","parent_record_id","record_type","chunk_title","chunk_text","keywords","entity_ids","source_id","source_title","source_page_pdf","room_location_code","element_code","damage_code","significance","language","access_level","citation_payload"],
    }.get(sheet, list(row.index))
    fields = []
    for col in priority:
        if col in row.index:
            val = clean(row[col])
            if val:
                fields.append(f"{col}: {val}")
    return "\n".join(fields)

@st.cache_data(show_spinner=False)
def load_records(path, mtime):
    records = []
    xls = pd.ExcelFile(path)
    for sheet, (label, record_type) in SHEET_CONFIG.items():
        if sheet not in xls.sheet_names:
            continue
        df = pd.read_excel(path, sheet_name=sheet).fillna("")
        for idx, row in df.iterrows():
            # Jangan tampilkan chunk bertanda internal pada chatbot publik.
            if sheet == "Chunk_RAG" and clean(row.get("access_level", "")).lower() != "public":
                continue
            content = row_to_text(sheet, row)
            if not content.strip():
                continue
            title_col = next((c for c in ["dc:title", "chunk_title"] if c in row.index and clean(row[c])), None)
            title = clean(row[title_col]) if title_col else f"{label} #{idx+1}"
            source_id = clean(row.get("record_id", "")) or clean(row.get("element_id", "")) or clean(row.get("damage_id", "")) or clean(row.get("policy_id", "")) or clean(row.get("chunk_id", "")) or clean(row.get("source_id", "")) or clean(row.get("dc:identifier", ""))
            source_title = clean(row.get("source_title", "")) or clean(row.get("dc:source", "")) or title
            page = clean(row.get("source_page_pdf", "")) or clean(row.get("pdf_pages", ""))
            url = clean(row.get("doc_url", ""))
            records.append({
                "id": source_id or f"{sheet}-{idx+1}",
                "title": title,
                "sheet": sheet,
                "label": label,
                "type": record_type,
                "text": content,
                "source_title": source_title,
                "page": page,
                "url": url,
            })
    # Chunk_RAG may duplicate some source records; keep it available because it contains curated passages.
    return records

def tokenize(text):
    return set(re.findall(r"[a-zA-ZÀ-ÿ0-9_-]+", text.lower()))

def lexical_search(query, records, top_k=5):
    # Pencarian kata kunci dengan perluasan istilah umum bahasa Indonesia.
    q = tokenize(query)
    aliases = {
        "rusak": {"kerusakan", "retak", "mengelupas", "terkelupas", "terkikis", "pecah"},
        "pintu": {"daun", "kusen", "pintu"},
        "jendela": {"kaca", "bingkai", "jendela"},
        "atap": {"dak", "kubah", "talang", "waterproofing"},
        "jumlah": {"jumlah", "quantity", "buah", "bidang"},
    }
    expanded = set(q)
    for token in q:
        expanded.update(aliases.get(token, set()))
    if not expanded:
        return []
    scored = []
    for rec in records:
        text = (rec["title"] + " " + rec["text"]).lower()
        terms = tokenize(text)
        overlap = len(expanded & terms)
        # Prioritaskan kecocokan pada judul dan kategori.
        title_terms = tokenize(rec["title"] + " " + rec["label"])
        title_overlap = len(expanded & title_terms)
        if overlap:
            score = overlap / max(1, len(expanded)) + 0.25 * title_overlap
            scored.append((score, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": float(score), "record": rec} for score, rec in scored[:top_k]]

def deterministic_count_answer(question, records):
    q = question.lower()
    asks_count = any(x in q for x in ["berapa", "jumlah", "total", "ada berapa"])
    asks_door = any(x in q for x in ["pintu", "daun pintu", "kusen pintu"])
    if not (asks_count and asks_door):
        return None
    damage_records = [r for r in records if r["sheet"] == "Inventarisasi_Kerusakan"
                      and any(x in (r["text"] + " " + r["title"]).lower()
                              for x in ["pintu", "daun pintu", "kusen pintu"])]
    if not damage_records:
        return "Saya belum menemukan rekod kerusakan pintu dalam data yang tersedia."
    ids = ", ".join(r["id"] for r in damage_records)
    return (f"Data mencatat **{len(damage_records)} rekod kerusakan yang berkaitan dengan pintu**, "
            "bukan jumlah fisik pintu yang rusak. Rekodnya meliputi daun pintu retak dan cat kusen pintu mengelupas. "
            f"ID rekod: {ids}. Jumlah pintu fisik yang terdampak belum dapat dipastikan dari data ini.")

def api_key():
    """Gemini API key dari Streamlit Secrets atau environment variable."""
    try:
        return st.secrets.get("GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    except Exception:
        return os.getenv("GEMINI_API_KEY", "")

def generation_model():
    """Pilih model generatif; default ke model stabil yang direkomendasikan saat ini."""
    try:
        return st.secrets.get("GEMINI_MODEL", "gemini-3.8-flash") or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    except Exception:
        return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

@st.cache_resource(show_spinner=False)
def gemini_client(key):
    from google import genai
    return genai.Client(api_key=key)

def embed_texts(client, texts):
    """Embedding Gemini untuk dokumen; diproses per batch kecil."""
    vectors = []
    for start in range(0, len(texts), 32):
        batch = texts[start:start+32]
        result = client.models.embed_content(
            model="gemini-embedding-001",
            contents=batch,
            config={"task_type": "RETRIEVAL_DOCUMENT", "output_dimensionality": 768},
        )
        vectors.extend([item.values for item in result.embeddings])
    return np.asarray(vectors, dtype=np.float32)

@st.cache_resource(show_spinner="Menyiapkan indeks pencarian semantik dengan Gemini…")
def build_semantic_index(key, fingerprint, serialized_records):
    # Serialized text makes cache invalidation explicit when the workbook changes.
    import json
    records = json.loads(serialized_records)
    client = gemini_client(key)
    texts = [r["title"] + "\n" + r["text"] for r in records]
    vectors = embed_texts(client, texts)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.maximum(norms, 1e-12)
    return records, vectors

def semantic_search(query, records, vectors, client, top_k=5):
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=query,
        config={"task_type": "RETRIEVAL_QUERY", "output_dimensionality": 768},
    )
    qvec = np.asarray(result.embeddings[0].values, dtype=np.float32)
    qvec = qvec / max(float(np.linalg.norm(qvec)), 1e-12)
    scores = vectors @ qvec
    indexes = np.argsort(scores)[::-1][:top_k]
    return [{"score": float(scores[i]), "record": records[int(i)]} for i in indexes]

def answer_with_rag(question, results, client):
    context_blocks = []
    for i, hit in enumerate(results, 1):
        r = hit["record"]
        context_blocks.append(
            f"[Sumber {i}]\nJudul: {r['title']}\nJenis data: {r['label']}\n"
            f"ID: {r['id']}\nDokumen sumber: {r['source_title']}\nHalaman: {r['page'] or 'Belum dicantumkan'}\n"
            f"Isi:\n{r['text']}\nURL: {r['url'] or 'Belum dicantumkan'}"
        )
    context = "\n\n---\n\n".join(context_blocks)
    system = """Anda adalah chatbot publikasi data dokumentasi Masjid Syuhada Yogyakarta.
Jawab dalam bahasa Indonesia yang jelas dan mudah dipahami. Gunakan HANYA konteks sumber yang diberikan.
Jangan mengarang fakta, lokasi rinci, tahun, bahan, kondisi, tingkat kerusakan, atau metode konservasi.
Bedakan fakta yang tertulis dari dugaan sumber. Jika data tidak tersedia atau perlu diverifikasi, katakan secara eksplisit.
Jika relevan, sertakan judul dokumen, ID rekod, dan halaman sumber. Jangan menyatakan bahwa jawaban merupakan penilaian teknis profesional.
Jika pertanyaan tidak dapat dijawab dari konteks, jelaskan keterbatasan data dan sarankan kata kunci lain."""
    prompt = f"Pertanyaan publik: {question}\n\nKonteks hasil retrieval:\n{context}\n\nJawab berdasarkan konteks dan cantumkan sumber yang digunakan."
    from google.genai import types
    response = client.models.generate_content(
        model=generation_model(),
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.1),
    )
    answer = getattr(response, "text", None)
    if not answer:
        raise RuntimeError("Gemini tidak mengembalikan teks jawaban. Periksa model dan kuota API.")
    return answer.strip()

if not DATA_PATH.exists():
    st.error("File Excel sumber tidak ditemukan. Pastikan file Metadata_DCMA_RAG_Masjid_Syuhada_101.xlsx berada satu folder dengan app.py.")
    st.stop()

mtime = DATA_PATH.stat().st_mtime
records = load_records(str(DATA_PATH), mtime)
key = api_key()

with st.sidebar:
    st.header("Tentang data")
    st.write("Sumber: workbook metadata dokumentasi Masjid Syuhada.")
    st.metric("Rekod yang dimuat", len(records))
    st.caption("Jawaban mengikuti informasi di workbook. Informasi yang belum terverifikasi akan ditandai.")
    st.divider()
    st.subheader("Filter jenis data")
    type_options = ["Semua jenis"] + sorted({r["label"] for r in records})
    chosen_type = st.selectbox("Tampilkan hasil dari", type_options)
    st.caption("Untuk publikasi terbuka, pastikan hak akses dokumen dan tautan sumber telah ditinjau.")

if not key:
    st.info("Mode pencarian kata kunci aktif. Untuk mengaktifkan RAG generatif dengan Google Gemini, tambahkan GEMINI_API_KEY di Streamlit Secrets. Tanpa API key, aplikasi tetap mencari rekod dan menampilkan sumbernya.")

# Chat history is session-local.
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Halo! Saya dapat membantu mencari informasi pada data dokumentasi Masjid Syuhada, seperti elemen arsitektur, material, catatan kerusakan, dokumen sumber, dan prioritas pelestarian. Apa yang ingin Anda ketahui?"
    }]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander("Lihat sumber data"):
                for hit in msg["sources"]:
                    r = hit["record"]
                    st.markdown(f"**{r['title']}** · `{r['id']}`")
                    st.caption(f"{r['label']} | Dokumen: {r['source_title']} | Halaman: {r['page'] or 'Belum dicantumkan'}")
                    if r["url"]:
                        st.markdown(f"[Buka dokumen sumber]({r['url']})")
                    with st.expander("Cuplikan rekod"):
                        st.text(r["text"][:2500])

question = st.chat_input("Tanyakan sesuatu tentang data Masjid Syuhada…")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    available_records = [r for r in records if chosen_type == "Semua jenis" or r["label"] == chosen_type]
    with st.chat_message("assistant"):
        with st.spinner("Menelusuri sumber data…"):
            try:
                direct_answer = deterministic_count_answer(question, available_records)
                if direct_answer:
                    hits = lexical_search("pintu kerusakan daun pintu kusen pintu", available_records, top_k=5)
                    response = direct_answer
                elif key:
                    import json
                    fingerprint = hashlib.sha256(
                        json.dumps([(r["id"], r["text"]) for r in available_records], ensure_ascii=False).encode("utf-8")
                    ).hexdigest()
                    # Index the full data once; apply the UI filter to retrieved hits afterward.
                    all_json = json.dumps(records, ensure_ascii=False)
                    all_fingerprint = hashlib.sha256(all_json.encode("utf-8")).hexdigest()
                    indexed_records, vectors = build_semantic_index(key, all_fingerprint, all_json)
                    client = gemini_client(key)
                    hits = semantic_search(question, indexed_records, vectors, client, top_k=min(8, len(indexed_records)))
                    if chosen_type != "Semua jenis":
                        filtered = [h for h in hits if h["record"]["label"] == chosen_type]
                        hits = filtered or lexical_search(question, available_records, top_k=5)
                    response = answer_with_rag(question, hits[:6], client) if hits else "Saya belum menemukan rekod yang cukup relevan. Coba gunakan istilah elemen, kode, material, jenis kerusakan, atau judul dokumen."
                else:
                    hits = lexical_search(question, available_records, top_k=5)
                    if hits:
                        response = "Saya menemukan rekod berikut berdasarkan kecocokan kata kunci. **Mode jawaban generatif belum aktif** karena GEMINI_API_KEY belum diatur. Silakan lihat sumber dan cuplikan di bawah untuk membaca data yang relevan."
                    else:
                        response = "Saya belum menemukan rekod yang cocok dengan kata kunci tersebut. Coba gunakan istilah lain, misalnya *atap dak beton*, *kaca jendela retak*, *Prioritas 1*, atau kode elemen."
                st.markdown(response)
                if hits:
                    with st.expander("Lihat sumber data yang digunakan", expanded=True):
                        for hit in hits[:6]:
                            r = hit["record"]
                            st.markdown(f"**{r['title']}** · `{r['id']}`")
                            st.caption(f"{r['label']} | Dokumen: {r['source_title']} | Halaman: {r['page'] or 'Belum dicantumkan'} | Skor relevansi: {hit['score']:.3f}")
                            if r["url"]:
                                st.markdown(f"[Buka dokumen sumber]({r['url']})")
                            st.write(r["text"][:1800])
                            st.divider()
                st.session_state.messages.append({"role": "assistant", "content": response, "sources": hits if hits else []})
            except Exception as exc:
                st.error("Terjadi kendala saat memproses pertanyaan. Periksa GEMINI_API_KEY, kuota/batas penggunaan Gemini API, dan log aplikasi.")
                st.caption(f"Detail teknis: {type(exc).__name__}: {exc}")
                st.session_state.messages.append({"role": "assistant", "content": "Maaf, pertanyaan belum berhasil diproses. Periksa konfigurasi API dan coba kembali."})

st.divider()
st.caption("Catatan: aplikasi ini adalah alat temu kembali informasi, bukan pengganti pemeriksaan lapangan, kajian konservasi, atau validasi oleh ahli cagar budaya.")
