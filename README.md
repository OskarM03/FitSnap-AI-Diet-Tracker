# FitSnap 🍎 - Inteligentny Dziennik Makroskładników

FitSnap to nowoczesna aplikacja webowa zbudowana w języku Python, służąca do śledzenia spożytych kalorii i makroskładników. Projekt odchodzi od ręcznego wpisywania danych na rzecz wykorzystania sztucznej inteligencji.

## 🚀 Główne funkcjonalności
* **Analiza obrazu:** Użytkownik robi zdjęcie posiłku, a model GPT-4o-mini rozpoznaje potrawę, szacuje jej gramaturę i automatycznie parsuje dane.
* **Rozpoznawanie mowy:** Integracja z API Whisper pozwala na dyktowanie posiłków naturalnym językiem (np. "Zjadłem 150g schabowego").
* **Logika Kameleona:** Aplikacja za pomocą wyrażeń regularnych samodzielnie decyduje, czy dany produkt z bazy powinien być rozliczany w gramach (np. "Jabłko (150g)"), czy w sztukach (np. "Zestaw Big Mac"), dynamicznie przebudowując interfejs dla użytkownika.
* **Auto-nauka bazy danych:** Jeśli AI wykryje jedzenie, którego nie ma w lokalnej bazie SQLite, wygeneruje dla niego makroskładniki (na 100g) i doda je na stałe do bazy podczas analizy.

## 🛠️ Stack Technologiczny
* **Python 3**
* **Streamlit** (Front-end i zarządzanie stanem aplikacji / session_state)
* **OpenAI API** (Modele Vision i Audio)
* **SQLite3** (Trwały zapis danych na dysku)
* **Pandas** (Przetwarzanie danych do wykresów)

## 🤝 Nota o architekturze i współpracy z AI
Podczas tworzenia tego projektu pełniłem rolę Product Managera oraz Architekta. Zaprojektowałem logikę działania aplikacji, system zakładek, strukturę bazy danych oraz innowacyjną "Logikę Kameleona" poprawiającą UX. 

Sam kod źródłowy oraz jego ostateczna refaktoryzacja (optymalizacja zgodnie z zasadą DRY) zostały wygenerowane we współpracy z modelami sztucznej inteligencji. Celem było wykorzystanie AI jako nowoczesnego narzędzia przyspieszającego wdrażanie koncepcji logicznych do produkcyjnego kodu.
