import streamlit as st
from openai import OpenAI
import base64
import json
import pandas as pd
import sqlite3
import uuid
from datetime import date
import re

# Inicjalizacja stanu sesji
if 'dziennik' not in st.session_state:
    st.session_state.dziennik = []
if 'zrobione_zdjecia' not in st.session_state:
    st.session_state.zrobione_zdjecia = []

# Konfiguracja API (docelowo przenieść klucz do zmiennych środowiskowych)
API_KEY = st.secrets["OPENAI_API_KEY"]
klient = OpenAI(api_key=API_KEY)
DB_PATH = "baza_jedzenia.db"
# Automatyczne tworzenie tabeli dla trwałego dziennika
polaczenie = sqlite3.connect(DB_PATH)
polaczenie.execute("""
    CREATE TABLE IF NOT EXISTS historia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT, danie TEXT, kalorie INTEGER, bialko INTEGER, 
        weglowodany INTEGER, tluszcze INTEGER, cukier INTEGER, sol INTEGER
    )
""")
polaczenie.commit()

# Wczytywanie dzisiejszych posiłków z bazy
dzisiaj = str(date.today())
dzisiejsze_posilki = pd.read_sql_query(
    "SELECT danie, kalorie, bialko, weglowodany, tluszcze, cukier, sol FROM historia WHERE data = ?", 
    polaczenie, params=(dzisiaj,)
)
polaczenie.close()

st.session_state.dziennik = dzisiejsze_posilki.to_dict('records')

st.markdown("""
<style>
    /* Zaokrąglone przyciski z efektem najechania */
    div.stButton > button:first-child {
        border-radius: 20px;
        border: 1px solid #2ECC71;
        transition: all 0.3s;
    }
    div.stButton > button:first-child:hover {
        background-color: #2ECC71;
        color: black;
        border: 1px solid #2ECC71;
    }
    /* Powiększone, estetyczne metryki (Kcal, Białko) */
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 800;
        color: #2ECC71;
    }
    /* Estetyczne ramki dla wgrywanych zdjęć */
    img {
        border-radius: 15px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="text-align: center; padding: 10px;">kla
    <h1 style="color: #2ECC71; font-size: 3.5rem; margin-bottom: 0px;">FitSnap 🍎</h1>
    <p style="color: #A0A0A0; font-size: 1.1rem;">Twój inteligentny dziennik makroskładników</p>
</div>
""", unsafe_allow_html=True)

# UI: Aparat i Galeria
zakladka_aparat, zakladka_galeria, zakladka_glos = st.tabs(["📸 Zrób zdjęcie", "🖼️ Galeria", "🎙️ Głos"])
zdjecia_do_analizy = []

with zakladka_aparat:
    nowe_zdjecie = st.camera_input("Aparat", key="kamera")
    if nowe_zdjecie:
        # Unikanie duplikatów w pamięci podręcznej
        if not any(z.getvalue() == nowe_zdjecie.getvalue() for z in st.session_state.zrobione_zdjecia):
            st.session_state.zrobione_zdjecia.append(nowe_zdjecie)
            st.rerun()
            
    if st.session_state.zrobione_zdjecia:
        kolumny = st.columns(min(len(st.session_state.zrobione_zdjecia), 4))
        for idx, z in enumerate(st.session_state.zrobione_zdjecia):
            with kolumny[idx % 4]:
                st.image(z, use_container_width=True)
                if st.button("❌ Usuń", key=f"usun_foto_{idx}"):
                    st.session_state.zrobione_zdjecia.pop(idx)
                    st.rerun()
        zdjecia_do_analizy.extend(st.session_state.zrobione_zdjecia)

with zakladka_galeria:
    zdjecia_galeria = st.file_uploader("Wybierz pliki", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    if zdjecia_galeria:
        zdjecia_do_analizy.extend(zdjecia_galeria)
        
with zakladka_glos:
    nagranie = st.audio_input("Nagraj co zjadłeś (np. 'Zjadłem 150g schabowego i 200g ziemniaków')")
    
    if nagranie:
        if st.button("🎤 Analizuj głos", key="btn_glos_analiza"):
            with st.spinner("Przetwarzam głos i szukam w bazie..."):
                nagranie.name = "audio.wav"
                transkrypcja = klient.audio.transcriptions.create(model="whisper-1", file=nagranie)
                st.session_state["ostatni_tekst"] = transkrypcja.text
                
                polaczenie = sqlite3.connect(DB_PATH)
                kursor = polaczenie.cursor()
                kursor.execute("SELECT nazwa FROM jedzenie")
                lista_nazw = [wiersz[0] for wiersz in kursor.fetchall()]
                polaczenie.close()
                
                prompt = f"""Jesteś precyzyjnym systemem dietetycznym. Użytkownik: "{st.session_state['ostatni_tekst']}".
                ZADANIE: Znajdź w podanej bazie danych zjedzone produkty. MUSISZ użyć dokładnych, pełnych nazw z listy: 
                {lista_nazw}
                
                Zwróć JSON:
                {{ "skladniki": [ {{"nazwa_z_bazy": "IDEALNIE_SKOPIOWANA_NAZWA_Z_LISTY", "mnoznik": 1.5}} ] }}
                
                ZASADY MNOŻNIKA (wielkości porcji):
                - Jeśli w bazie produkt to "Schabowy w panierce [100g]", a użytkownik mówi "200g", mnożnik = 2.0.
                - Jeśli użytkownik NIE PODAJE wagi (mówi "zjadłem schabowego"), SAM ZGADNIJ średnią porcję i ustaw mnożnik np. na 1.5 lub 2.0, w zależności od tego, ile waży przeciętny obiad.
                - Dopasowuj nazwy na logikę (dla słowa "ziemniaki", wybierz "Ziemniaki gotowane [100g]" itp.).
                """
                
                odp = klient.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": prompt}]
                )
                
                rozpoznanie = json.loads(odp.choices[0].message.content)
                
                # Zapisujemy tylko te, które w 100% pasują do bazy
                st.session_state["robocze_skladniki_glos"] = {
                    sk["nazwa_z_bazy"]: float(sk.get("mnoznik", 1.0)) 
                    for sk in rozpoznanie.get("skladniki", []) if sk["nazwa_z_bazy"] in lista_nazw
                }
                st.rerun()

    # Dynamiczny interfejs edycji (Poczekalnia)
    # Dynamiczny interfejs edycji (Poczekalnia)
    if "robocze_skladniki_glos" in st.session_state:
        st.markdown("### ⚙️ Dopasuj ilości")
        if "ostatni_tekst" in st.session_state:
            st.caption(f"Usłyszałem: {st.session_state['ostatni_tekst']}")
        
        polaczenie = sqlite3.connect(DB_PATH)
        kursor = polaczenie.cursor()
        kursor.execute("SELECT nazwa, kalorie, bialko, weglowodany, tluszcze, cukier, sol FROM jedzenie")
        dania_db = kursor.fetchall()
        polaczenie.close()
        slownik_dan = {d[0]: d for d in dania_db}
        
        wybrane_dania = st.multiselect(
            "Produkty w tym posiłku (dodaj brakujące, jeśli AI się pomyliło):", 
            options=list(slownik_dan.keys()), 
            default=list(st.session_state["robocze_skladniki_glos"].keys()),
            key="multi_glos_nowy"
        )
        
        suma_k = suma_b = suma_w = suma_t = suma_c = suma_s = 0
        uzyte_etykiety = []
        
        # --- Rysowanie estetycznej tabeli dla zdjęć ---
        # --- Rysowanie estetycznej tabeli dla głosu ---
        if wybrane_dania:
            st.markdown("---")
            naglowek1, naglowek2, naglowek3, naglowek4, naglowek5, naglowek6 = st.columns([2.5, 1.5, 1.5, 1.2, 1.2, 1.2])
            naglowek1.markdown("**Produkt**")
            naglowek2.markdown("**Porcja (x)**")
            naglowek3.markdown("**Kcal**")
            naglowek4.markdown("**B(g)**")
            naglowek5.markdown("**W(g)**")
            naglowek6.markdown("**T(g)**")
            
            for danie in wybrane_dania:
                wiersz = slownik_dan[danie]
                czysta_nazwa = danie.split('(')[0].strip()
                
                kol1, kol2, kol3, kol4, kol5, kol6 = st.columns([2.5, 1.5, 1.5, 1.2, 1.2, 1.2])
                kol1.write(f"🍽️ {czysta_nazwa}")
                
                domyslny_mnoznik = st.session_state["robocze_skladniki_glos"].get(danie, 1.0)
                
                nowy_mnoznik = kol2.number_input(
                    "Mnożnik", 
                    min_value=0.1, max_value=20.0, value=float(domyslny_mnoznik), step=0.1, 
                    key=f"suwak_glos_{danie}",
                    label_visibility="collapsed"
                )
                
                # Zmienne bazowe reagujące na mnożnik
                baza_k = int(wiersz[1] * nowy_mnoznik)
                baza_b = int(wiersz[2] * nowy_mnoznik)
                baza_w = int(wiersz[3] * nowy_mnoznik)
                baza_t = int(wiersz[4] * nowy_mnoznik)
                
                # Edytowalne pola makroskładników nadpisujące bazę
                k_prod = kol3.number_input("Kcal", value=baza_k, key=f"k_glos_{danie}", label_visibility="collapsed")
                b_prod = kol4.number_input("B", value=baza_b, key=f"b_glos_{danie}", label_visibility="collapsed")
                w_prod = kol5.number_input("W", value=baza_w, key=f"w_glos_{danie}", label_visibility="collapsed")
                t_prod = kol6.number_input("T", value=baza_t, key=f"t_glos_{danie}", label_visibility="collapsed")
                
                suma_k += k_prod
                suma_b += b_prod
                suma_w += w_prod
                suma_t += t_prod
                suma_c += int(wiersz[5] * nowy_mnoznik)
                suma_s += int(wiersz[6] * nowy_mnoznik)
                
                uzyte_etykiety.append(f"{czysta_nazwa} [{nowy_mnoznik}x]")
            st.markdown("---")
        
        # Pasek podsumowania z żywym przeliczaniem całkowitych kalorii
        st.success(f"**Razem cały posiłek:** 🔥 {suma_k} kcal | B: {suma_b}g | W: {suma_w}g | T: {suma_t}g")
        
        if st.button("✅ Zatwierdź posiłek", use_container_width=True):
            pelna_nazwa = " + ".join(uzyte_etykiety) if uzyte_etykiety else "Pusty posiłek"
            
            polaczenie = sqlite3.connect(DB_PATH)
            polaczenie.execute(
                "INSERT INTO historia (data, danie, kalorie, bialko, weglowodany, tluszcze, cukier, sol) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (dzisiaj, pelna_nazwa, suma_k, suma_b, suma_w, suma_t, suma_c, suma_s)
            )
            polaczenie.commit()
            polaczenie.close()
            
            st.session_state.dziennik.append({
                "danie": pelna_nazwa, "kalorie": suma_k, "bialko": suma_b, 
                "weglowodany": suma_w, "tluszcze": suma_t, "cukier": suma_c, "sol": suma_s
            })
            
            del st.session_state["robocze_skladniki_glos"]
            if "ostatni_tekst" in st.session_state:
                del st.session_state["ostatni_tekst"]
            st.rerun()

    # Formularz wyciągnięty na zewnątrz przycisku
    if "ostatni_tekst" in st.session_state:
        st.info(f"Usłyszałem: {st.session_state['ostatni_tekst']}")

    if "wynik_glos" in st.session_state:
        dane = st.session_state["wynik_glos"]
        
        polaczenie = sqlite3.connect(DB_PATH)
        kursor = polaczenie.cursor()
        kursor.execute("SELECT nazwa, kalorie, bialko, weglowodany, tluszcze, cukier, sol FROM jedzenie ORDER BY nazwa ASC")
        dania_db = kursor.fetchall()
        polaczenie.close()
        
        slownik_dan = {d[0]: d for d in dania_db}
        
        wybrane = st.multiselect(
            "Błąd detekcji? Wybierz ręcznie z bazy:",
            options=list(slownik_dan.keys()),
            default=[],
            key="multi_glos"
        )
        
        v_nazwa, v_kcal, v_b, v_w, v_t, v_c, v_s = dane.get('danie',''), dane.get('kalorie',0), dane.get('bialko',0), dane.get('weglowodany',0), dane.get('tluszcze',0), dane.get('cukier',0), dane.get('sol',0)
        
        if wybrane:
            v_kcal = sum([slownik_dan[n][1] for n in wybrane])
            v_b = sum([slownik_dan[n][2] for n in wybrane])
            v_w = sum([slownik_dan[n][3] for n in wybrane])
            v_t = sum([slownik_dan[n][4] for n in wybrane])
            v_c = sum([slownik_dan[n][5] for n in wybrane])
            v_s = sum([slownik_dan[n][6] for n in wybrane])
            v_nazwa = " + ".join(wybrane)
        
        with st.form(key="form_glos"):
            nowa_nazwa = st.text_input("Danie", value=v_nazwa)
            
            c1, c2, c3 = st.columns(3)
            n_kcal = c1.number_input("Kcal", value=int(v_kcal), key="k_g")
            n_b = c2.number_input("Białko (g)", value=int(v_b), key="b_g")
            n_w = c3.number_input("Węgle (g)", value=int(v_w), key="w_g")
            
            c4, c5, c6 = st.columns(3)
            n_t = c4.number_input("Tłuszcz (g)", value=int(v_t), key="t_g")
            n_c = c5.number_input("Cukier (g)", value=int(v_c), key="c_g")
            n_s = c6.number_input("Sól (g)", value=int(v_s), key="s_g")

            if st.form_submit_button("Zatwierdź posiłek głosowy"):
                polaczenie = sqlite3.connect(DB_PATH)
                polaczenie.execute(
                    "INSERT INTO historia (data, danie, kalorie, bialko, weglowodany, tluszcze, cukier, sol) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (dzisiaj, nowa_nazwa, n_kcal, n_b, n_w, n_t, n_c, n_s)
                )
                polaczenie.commit()
                polaczenie.close()
                
                # Natychmiastowe wrzucenie danych do dziennika na dole ekranu
                st.session_state.dziennik.append({
                    "danie": nowa_nazwa, "kalorie": n_kcal, 
                    "bialko": n_b, "weglowodany": n_w, 
                    "tluszcze": n_t, "cukier": n_c, "sol": n_s
                })
                
                del st.session_state["wynik_glos"]
                if "ostatni_tekst" in st.session_state:
                    del st.session_state["ostatni_tekst"]
                st.rerun()
# Analiza i korekta
if zdjecia_do_analizy:
    for zdjecie in zdjecia_do_analizy:
        st.markdown("---")
        img_id = f"{zdjecie.name}_{zdjecie.size}"
        
        kol1, kol2 = st.columns([1, 2])
        with kol1:
            st.image(zdjecie, caption="Podgląd", use_container_width=True)
            
        with kol2:
            # 1. Faza analizy AI (Inteligentne dodawanie nowych dań i mnożniki)
            if f"robocze_{img_id}" not in st.session_state:
                if st.button("🔍 Analizuj posiłek", key=f"btn_{img_id}"):
                    with st.spinner("AI analizuje zdjęcie, czyta gramatury i weryfikuje bazę..."):
                        img_base64 = base64.b64encode(zdjecie.getvalue()).decode("utf-8")
                        
                        polaczenie = sqlite3.connect(DB_PATH)
                        kursor = polaczenie.cursor()
                        kursor.execute("SELECT nazwa FROM jedzenie")
                        lista_nazw = [wiersz[0] for wiersz in kursor.fetchall()]
                        polaczenie.close()
                        
                        prompt = f"""Jesteś wybitnym asystentem dietetycznym. 
                        Twoja obecna baza produktów: {lista_nazw}
                        
                        ZASADY:
                        1. Jeśli to, co na zdjęciu, pasuje do czegoś z bazy, użyj DOKŁADNEJ nazwy z bazy.
                        2. Jeśli produktu NIE MA w bazie (np. nowe warzywo, danie), STWÓRZ GO. Nadaj mu czytelną nazwę z dopiskiem "(100g)" np. "Mizeria (100g)" i podaj szacunkowe makroskładniki dla 100 gramów.
                        3. Określ 'mnoznik':
                           - Jeśli w bazie produkt nazywa się "Jabłko (150g)", a na zdjęciu widzisz pół jabłka, mnoznik = 0.5.
                           - Jeśli stworzyłeś "Mizeria (100g)", a na zdjęciu leży 250g, mnoznik = 2.5.
                           - Jeśli to gotowe danie bez gramów, np. "Big Mac", a na zdjęciu jest jeden, mnoznik = 1.0.
                        
                        Zwróć JSON:
                        {{
                            "skladniki": [
                                {{
                                    "nazwa": "Nazwa z bazy lub nowa",
                                    "mnoznik": 1.0,
                                    "w_bazie": true_lub_false,
                                    "kcal": 100, "b": 5, "w": 10, "t": 2, "c": 1, "s": 0
                                }}
                            ]
                        }}
                        (Makroskładniki są wymagane tylko jeśli w_bazie=false, odnoś je zawsze do tej wagi, która jest w nawiasie nazwy).
                        """
                        
                        odp = klient.chat.completions.create(
                            model="gpt-4o-mini",
                            response_format={"type": "json_object"},
                            messages=[{"role": "user", "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                            ]}]
                        )
                        
                        rozpoznanie = json.loads(odp.choices[0].message.content)
                        
                        polaczenie = sqlite3.connect(DB_PATH)
                        kursor = polaczenie.cursor()
                        robocze_dane = {}
                        
                        for sk in rozpoznanie.get("skladniki", []):
                            nazwa = sk.get("nazwa")
                            mnoznik = float(sk.get("mnoznik", 1.0))
                            
                            # Automatyczne dodawanie nowości z AI na stałe do Twojej bazy
                            if not sk.get("w_bazie") and nazwa not in lista_nazw:
                                kursor.execute(
                                    "INSERT INTO jedzenie (nazwa, kalorie, bialko, weglowodany, tluszcze, cukier, sol) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (nazwa, sk.get("kcal",0), sk.get("b",0), sk.get("w",0), sk.get("t",0), sk.get("c",0), sk.get("s",0))
                                )
                                polaczenie.commit()
                                
                            robocze_dane[nazwa] = mnoznik
                            
                        polaczenie.close()
                        st.session_state[f"robocze_{img_id}"] = robocze_dane
                        st.rerun()

            # 2. Faza korekty - Interfejs czytający wagi w locie
            if f"robocze_{img_id}" in st.session_state:
                st.markdown("### ⚙️ Dopasuj i edytuj posiłek")
                
                polaczenie = sqlite3.connect(DB_PATH)
                kursor = polaczenie.cursor()
                kursor.execute("SELECT nazwa, kalorie, bialko, weglowodany, tluszcze, cukier, sol FROM jedzenie ORDER BY nazwa ASC")
                dania_db = kursor.fetchall()
                polaczenie.close()
                
                slownik_dan = {d[0]: d for d in dania_db}
                
                wybrane = st.multiselect(
                    "Wykryte produkty (możesz dodać braki ręcznie):",
                    options=list(slownik_dan.keys()),
                    default=list(st.session_state[f"robocze_{img_id}"].keys()),
                    key=f"multi_{img_id}"
                )
                
                if wybrane:
                    st.markdown("---")
                    suma_k = suma_b = suma_w = suma_t = suma_c = suma_s = 0
                    uzyte_etykiety = []
                    
                    for danie in wybrane:
                        wiersz = slownik_dan[danie]
                        zapisany_mnoznik = st.session_state[f"robocze_{img_id}"].get(danie, 1.0)
                        czysta_nazwa = danie.split('(')[0].strip()
                        
                        # --- LOGIKA KAMELEONA (Python czyta nawiasy) ---
                        match = re.search(r'(\d+)\s*(g|ml)', danie.lower())
                        if match:
                            baza_waga = float(match.group(1)) # np. wyciąga '150' z 'Jabłko (150g)'
                            jednostka = match.group(2) # 'g' lub 'ml'
                            tryb_gramowy = True
                        else:
                            baza_waga = 1.0
                            jednostka = "szt/porcja"
                            tryb_gramowy = False

                        # Podsumowanie dla jednej pozycji
                        baza_k = int(wiersz[1] * zapisany_mnoznik)
                        baza_b = int(wiersz[2] * zapisany_mnoznik)
                        baza_w = int(wiersz[3] * zapisany_mnoznik)
                        baza_t = int(wiersz[4] * zapisany_mnoznik)
                        
                        kol_nazwa, kol_info = st.columns([3, 2])
                        kol_nazwa.markdown(f"#### 🍽️ {czysta_nazwa}")
                        kol_info.markdown(f"<div style='text-align: right; color: #2ECC71; margin-top: 10px;'>🔥 {baza_k} kcal | B: {baza_b}g | W: {baza_w}g | T: {baza_t}g</div>", unsafe_allow_html=True)
                        
                        with st.expander(f"✏️ Edytuj wartości odżywcze"):
                            st.caption(f"💡 AI wyciągnęło ten składnik z bazy jako: **{danie}**")
                            
                            # Okienko edycji ilości dostosowuje się do tego, co odczytało
                            if tryb_gramowy:
                                podana_waga = st.number_input(
                                    f"Waga całkowita na talerzu ({jednostka})", 
                                    min_value=1.0, max_value=5000.0, value=float(zapisany_mnoznik * baza_waga), step=10.0, 
                                    key=f"suwak_img_{img_id}_{danie}"
                                )
                                nowy_mnoznik = podana_waga / baza_waga
                            else:
                                nowy_mnoznik = st.number_input(
                                    "Ilość (sztuki / porcje)", 
                                    min_value=0.1, max_value=50.0, value=float(zapisany_mnoznik), step=0.5, 
                                    key=f"suwak_img_{img_id}_{danie}"
                                )
                            
                            # Odświeżenie przy ruchu suwakiem
                            if nowy_mnoznik != zapisany_mnoznik:
                                st.session_state[f"robocze_{img_id}"][danie] = nowy_mnoznik
                                st.rerun()
                                
                            baza_k_nowa = int(wiersz[1] * nowy_mnoznik)
                            baza_b_nowa = int(wiersz[2] * nowy_mnoznik)
                            baza_w_nowa = int(wiersz[3] * nowy_mnoznik)
                            baza_t_nowa = int(wiersz[4] * nowy_mnoznik)
                            baza_c_nowa = int(wiersz[5] * nowy_mnoznik)
                            baza_s_nowa = int(wiersz[6] * nowy_mnoznik)
                            
                            st.caption("Wyliczone pełne makro (możesz edytować liczby bezpośrednio):")
                            
                            k1, k2, k3 = st.columns(3)
                            k_prod = k1.number_input("Kcal", value=baza_k_nowa, key=f"k_{img_id}_{danie}")
                            b_prod = k2.number_input("Białko (g)", value=baza_b_nowa, key=f"b_{img_id}_{danie}")
                            w_prod = k3.number_input("Węgle (g)", value=baza_w_nowa, key=f"w_{img_id}_{danie}")
                            
                            k4, k5, k6 = st.columns(3)
                            t_prod = k4.number_input("Tłuszcze (g)", value=baza_t_nowa, key=f"t_{img_id}_{danie}")
                            c_prod = k5.number_input("Cukier (g)", value=baza_c_nowa, key=f"c_{img_id}_{danie}")
                            s_prod = k6.number_input("Sól (g)", value=baza_s_nowa, key=f"s_{img_id}_{danie}")
                            
                            if st.button(f"Zatwierdź zmiany w makro dla {czysta_nazwa}", key=f"potwierdz_{img_id}_{danie}"):
                                st.rerun()
                                
                        suma_k += k_prod
                        suma_b += b_prod
                        suma_w += w_prod
                        suma_t += t_prod
                        suma_c += c_prod
                        suma_s += s_prod
                        
                        if tryb_gramowy:
                            uzyte_etykiety.append(f"{czysta_nazwa} [{int(zapisany_mnoznik * baza_waga)}{jednostka}]")
                        else:
                            uzyte_etykiety.append(f"{czysta_nazwa} [{zapisany_mnoznik}x]")
                        
                    st.markdown("---")
                    
                    st.success(f"**Całe zdjęcie:** 🔥 {suma_k} kcal | B: {suma_b}g | W: {suma_w}g | T: {suma_t}g")
                    
                    if st.button("✅ Zapisz ten posiłek do dziennika", use_container_width=True, key=f"btn_zatwierdz_{img_id}"):
                        pelna_nazwa = " + ".join(uzyte_etykiety) if uzyte_etykiety else "Pusty posiłek"
                        
                        polaczenie = sqlite3.connect(DB_PATH)
                        polaczenie.execute(
                            "INSERT INTO historia (data, danie, kalorie, bialko, weglowodany, tluszcze, cukier, sol) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (dzisiaj, pelna_nazwa, suma_k, suma_b, suma_w, suma_t, suma_c, suma_s)
                        )
                        polaczenie.commit()
                        polaczenie.close()
                        
                        st.session_state.dziennik.append({
                            "danie": pelna_nazwa, "kalorie": suma_k, "bialko": suma_b, 
                            "weglowodany": suma_w, "tluszcze": suma_t, "cukier": suma_c, "sol": suma_s
                        })
                        
                        del st.session_state[f"robocze_{img_id}"]
                        if zdjecie in st.session_state.zrobione_zdjecia:
                            st.session_state.zrobione_zdjecia.remove(zdjecie)
                        st.rerun()

# Podsumowanie Dziennika
if st.session_state.dziennik:
    st.markdown("---")
    st.subheader("📊 Dziennik Spożycia")
    
    suma_kcal = sum(p['kalorie'] for p in st.session_state.dziennik)
    suma_b = sum(p['bialko'] for p in st.session_state.dziennik)
    suma_w = sum(p['weglowodany'] for p in st.session_state.dziennik)
    suma_t = sum(p['tluszcze'] for p in st.session_state.dziennik)
    suma_c = sum(p['cukier'] for p in st.session_state.dziennik)
    suma_s = sum(p['sol'] for p in st.session_state.dziennik)
    
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Kcal", suma_kcal)
    k2.metric("Białko", f"{suma_b}g")
    k3.metric("Węgle", f"{suma_w}g")
    k4.metric("Tłuszcz", f"{suma_t}g")
    k5.metric("Cukier", f"{suma_c}g")
    k6.metric("Sól", f"{suma_s}g")
    
    wykres = pd.DataFrame({
        "Makro": ["Białko", "Węglowodany", "Tłuszcze", "Cukier", "Sól"],
        "Ilość (g)": [suma_b, suma_w, suma_t, suma_c, suma_s]
    }).set_index("Makro")
    st.bar_chart(wykres)
    
    for idx, posilek in enumerate(st.session_state.dziennik):
        st.markdown(f"""
        <div style="background-color: #1E212B; padding: 15px; border-radius: 12px; margin-bottom: 12px; border-left: 6px solid #2ECC71; box-shadow: 2px 2px 10px rgba(0,0,0,0.15);">
            <h4 style="margin: 0; color: #FAFAFA; font-size: 16px;">🍽️ {posilek['danie']}</h4>
            <p style="margin: 0; margin-top: 6px; color: #CCCCCC; font-size: 14px;">
                🔥 <b style="color:#2ECC71;">{posilek['kalorie']} kcal</b> &nbsp;|&nbsp; 🥩 B: {posilek['bialko']}g &nbsp;|&nbsp; 🍞 W: {posilek['weglowodany']}g &nbsp;|&nbsp; 🥑 T: {posilek['tluszcze']}g
            </p>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---")
    CEL_KCAL = 2500
    st.progress(min(suma_kcal / CEL_KCAL, 1.0))
    st.write(f"Cel: {suma_kcal} / {CEL_KCAL} kcal")
    
    if suma_kcal > CEL_KCAL:
        st.error("Przekroczono limit kalorii!")

    if st.button("Wyczyść dzisiejszy dziennik"):
        polaczenie = sqlite3.connect(DB_PATH)
        polaczenie.execute("DELETE FROM historia WHERE data = ?", (dzisiaj,))
        polaczenie.commit()
        polaczenie.close()
        st.rerun()
        
        # 5. Przeglądanie historii z poprzednich dni
    st.markdown("---")
    with st.expander("📅 Sprawdź historię poprzednich dni"):
        wybrana_data = st.date_input("Wybierz datę do sprawdzenia:", value=date.today(), key="data_historia")
        
        if str(wybrana_data) != dzisiaj:
            polaczenie = sqlite3.connect(DB_PATH)
            historia_dnia = pd.read_sql_query(
                "SELECT danie, kalorie, bialko, weglowodany, tluszcze, cukier, sol FROM historia WHERE data = ?", 
                polaczenie, params=(str(wybrana_data),)
            )
            polaczenie.close()
            
            if not historia_dnia.empty:
                suma_hist_k = historia_dnia['kalorie'].sum()
                suma_hist_b = historia_dnia['bialko'].sum()
                suma_hist_w = historia_dnia['weglowodany'].sum()
                suma_hist_t = historia_dnia['tluszcze'].sum()
                suma_hist_c = historia_dnia['cukier'].sum()
                suma_hist_s = historia_dnia['sol'].sum()
                
                st.metric("Suma kalorii w tym dniu", f"{suma_hist_k} kcal")
                
                wykres_hist = pd.DataFrame({
                    "Makro": ["Białko", "Węglowodany", "Tłuszcze", "Cukier", "Sól"],
                    "Ilość (g)": [suma_hist_b, suma_hist_w, suma_hist_t, suma_hist_c, suma_hist_s]
                }).set_index("Makro")
                st.bar_chart(wykres_hist)
                
                st.dataframe(historia_dnia, use_container_width=True, hide_index=True)
            else:
                st.info("Brak zapisanych posiłków w tym dniu.")
