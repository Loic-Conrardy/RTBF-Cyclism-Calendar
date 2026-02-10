import requests
from ics import Calendar, Event
import dateutil.parser
import sys

# --- TA DÉCOUVERTE ---
# L'ID 23833 correspond spécifiquement aux "Prochains directs cyclisme"
WIDGET_URL = "https://bff-service.rtbf.be/auvio/v1.23/widgets/23833"

# Headers pour imiter un navigateur
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://auvio.rtbf.be",
    "Referer": "https://auvio.rtbf.be/"
}


def generate_final_calendar():
    cal = Calendar()
    found_count = 0

    print(f"📡 Appel du widget Cyclisme RTBF ({WIDGET_URL})...")

    try:
        r = requests.get(WIDGET_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()  # Lève une erreur si ce n'est pas 200 OK

        data = r.json()

        # --- ANALYSE BASÉE SUR TON IMAGE JSON ---
        # La liste se trouve dans data -> data -> content
        # On utilise .get() pour éviter que ça plante si le chemin change légèrement
        items = data.get('data', {}).get('content', [])

        print(f"📦 L'API a renvoyé {len(items)} éléments.")

        if not items:
            print("🤷 Aucun prochain direct cyclisme n'est listé pour le moment.")
            return

        for item in items:
            # On prend tout sans filtrer ! C'est déjà du vélo.
            title = item.get('title', 'Direct Cyclisme').strip()
            subtitle = item.get('subtitle', '').strip()

            # Gestion des dates (champs vus dans ta capture d'écran)
            start_str = item.get('scheduledFrom')
            end_str = item.get('scheduledTo')

            if start_str and end_str:
                e = Event()
                e.name = f"🚴 {title}"
                if subtitle: e.name += f" - {subtitle}"

                # Parsing intelligent des dates ISO 8601
                e.begin = dateutil.parser.parse(start_str)
                e.end = dateutil.parser.parse(end_str)

                # Construction de l'URL (le champ 'path' contient la fin de l'URL)
                path = item.get('path')
                if path:
                    e.url = f"https://auvio.rtbf.be{path}"
                else:
                    e.url = "https://auvio.rtbf.be/direct"

                # Description
                label = item.get('label', '')  # ex: "Prochain direct"
                channel = item.get('channelLabel', 'RTBF')
                e.description = f"{label} sur {channel}.\nLien : {e.url}"

                cal.events.add(e)
                found_count += 1
                # Affiche la date de façon lisible
                print(f"✅ AJOUTÉ : {e.name} | Le {e.begin.strftime('%d/%m à %Hh%M')}")

    except requests.exceptions.HTTPError as errh:
        print(f"❌ Erreur HTTP : {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"❌ Erreur de connexion : {errc}")
    except Exception as err:
        print(f"❌ Erreur inattendue : {err}")

    # Sauvegarde finale
    if found_count > 0:
        filename = "rtbf_cyclisme_final.ics"
        # Encoding utf-8 essentiel pour les accents
        with open(filename, "w", encoding='utf-8') as f:
            f.writelines(cal.serialize())
        print(f"\n🎉 SUCCÈS ! Fichier '{filename}' créé avec {found_count} courses.")
        print("-> Importe ce fichier dans Google Agenda (Paramètres > Importer).")


if __name__ == "__main__":
    generate_final_calendar()