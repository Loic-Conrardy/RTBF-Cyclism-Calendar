import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
import datetime
import re
from zoneinfo import ZoneInfo
import dateutil.parser

# ==========================================
# CONSTANTES ET CONFIGURATIONS
# ==========================================

# Dictionnaire pour la traduction des mois (RTL)
MOIS_FR = {
    'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12, 'decembre': 12
}

# Configuration de l'API RTBF
WIDGET_URL = "https://bff-service.rtbf.be/auvio/v1.23/widgets/23833"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://auvio.rtbf.be",
    "Referer": "https://auvio.rtbf.be/"
}


# ==========================================
# FONCTIONS UTILITAIRES
# ==========================================

def extraire_date_heure_rtl(date_texte, texte_diffusion):
    """Transforme les dates textuelles de RTL en objet datetime"""
    annee_actuelle = datetime.datetime.now().year

    jour = 1
    match_jour = re.search(r'\b(\d{1,2}|1er)\b', date_texte)
    if match_jour:
        jour = int(match_jour.group(1).replace('er', ''))

    mois = 1
    for mot in date_texte.lower().split():
        if mot in MOIS_FR:
            mois = MOIS_FR[mot]
            break

    heure, minute = 12, 0
    match_heure = re.search(r'(\d{1,2})h(\d{2})?', texte_diffusion.lower())
    if match_heure:
        heure = int(match_heure.group(1))
        if match_heure.group(2):
            minute = int(match_heure.group(2))

    fuseau = ZoneInfo("Europe/Brussels")
    mois_actuel = datetime.datetime.now().month
    if mois < mois_actuel and mois_actuel > 10:
        annee_actuelle += 1

    return datetime.datetime(annee_actuelle, mois, jour, heure, minute, tzinfo=fuseau)


# ==========================================
# SCRAPERS
# ==========================================

def ajouter_evenements_rtl(calendrier):
    """Récupère les diffusions RTL et les ajoute au calendrier"""
    print("\nRecherche des courses sur RTL...")
    url = "https://cyclismerevue.be/programme-tv-cyclisme/"
    compteur = 0

    try:
        reponse = requests.get(url, timeout=10)
        reponse.raise_for_status()
        soup = BeautifulSoup(reponse.text, 'html.parser')

        for li in soup.find_all('li'):
            texte_diffusion = li.get_text(strip=True)
            if 'RTL' in texte_diffusion.upper():
                parent_ul = li.find_parent('ul')
                if parent_ul and parent_ul.find_parent('li'):
                    course_li = parent_ul.find_parent('li')

                    course_nom = course_li.contents[0]
                    course_nom = course_nom.text.strip() if hasattr(course_nom, 'text') else str(course_nom).strip()
                    course_nom = course_nom.replace('–', '-').strip()

                    element_courant = course_li.find_parent('ul')
                    date_texte = ""
                    while element_courant:
                        element_courant = element_courant.find_previous_sibling()
                        if element_courant and element_courant.name in ['h2', 'h3', 'h4']:
                            date_texte = element_courant.get_text(strip=True)
                            break

                    if date_texte:
                        date_debut = extraire_date_heure_rtl(date_texte, texte_diffusion)

                        evenement = Event()
                        evenement.name = f"🚴‍♂️ [RTL] {course_nom}"
                        evenement.begin = date_debut
                        evenement.duration = datetime.timedelta(hours=2, minutes=30)
                        evenement.description = f"Diffusion : {texte_diffusion}\nSource : {url}"
                        evenement.location = "RTL"

                        calendrier.events.add(evenement)
                        compteur += 1
                        print(f"  Ajouté : {course_nom} | {date_debut.strftime('%d/%m à %H:%M')}")

    except Exception as e:
        print(f"  Erreur RTL : {e}")

    return compteur


def ajouter_evenements_rtbf(calendrier):
    """Récupère les diffusions RTBF via leur API et les ajoute au calendrier"""
    print("\nAppel du widget Cyclisme RTBF...")
    compteur = 0

    try:
        r = requests.get(WIDGET_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get('data', {}).get('content', [])

        if not items:
            print("  Aucun direct RTBF listé pour le moment.")
            return 0

        for item in items:
            title = item.get('title', 'Direct Cyclisme').strip()
            subtitle = item.get('subtitle', '').strip()
            start_str = item.get('scheduledFrom')
            end_str = item.get('scheduledTo')

            if start_str and end_str:
                e = Event()
                e.name = f"🚴 [RTBF] {title}"
                if subtitle: e.name += f" - {subtitle}"

                e.begin = dateutil.parser.parse(start_str)
                e.end = dateutil.parser.parse(end_str)

                path = item.get('path')
                e.url = f"https://auvio.rtbf.be{path}" if path else "https://auvio.rtbf.be/direct"

                label = item.get('label', '')
                channel = item.get('channelLabel', 'RTBF')
                e.description = f"{label} sur {channel}.\nLien : {e.url}"
                e.location = channel

                calendrier.events.add(e)
                compteur += 1

                # Formatage de l'affichage en tenant compte des fuseaux locaux (pour la console)
                debut_local = e.begin.astimezone(ZoneInfo("Europe/Brussels"))
                fin_local = e.end.astimezone(ZoneInfo("Europe/Brussels"))
                print(
                    f"  Ajouté : {e.name} | {debut_local.strftime('%d/%m de %H:%M')} à {fin_local.strftime('%H:%M')}")

    except Exception as e:
        print(f"  Erreur RTBF : {e}")

    return compteur


# ==========================================
# LANCEMENT PRINCIPAL
# ==========================================

def generer_calendrier_global():
    calendrier = Calendar()

    print("=== GÉNÉRATION DU CALENDRIER CYCLISTE BELGE ===")

    # On peuple le calendrier avec nos deux sources
    total_rtl = ajouter_evenements_rtl(calendrier)
    total_rtbf = ajouter_evenements_rtbf(calendrier)

    total_courses = total_rtl + total_rtbf

    # Sauvegarde
    if total_courses > 0:
        nom_fichier = "rtbf_cyclisme_final.ics"
        with open(nom_fichier, 'w', encoding='utf-8') as f:
            f.writelines(calendrier.serialize())

        print("\n" + "=" * 50)
        print(f"SUCCÈS ! Fichier '{nom_fichier}' généré.")
        print(f"Bilan : {total_rtl} course(s) RTL + {total_rtbf} course(s) RTBF = {total_courses} événements.")
        print("-> Importez ce fichier dans Google Agenda, Outlook ou Apple Calendar.")
        print("=" * 50 + "\n")
    else:
        print("\n⚠️ Aucune course n'a été trouvée sur aucune des chaînes. Le fichier n'a pas été créé.")


if __name__ == "__main__":
    generer_calendrier_global()