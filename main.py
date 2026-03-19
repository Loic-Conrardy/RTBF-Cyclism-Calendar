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

# Dictionnaire pour la traduction des mois
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

def extraire_date_heure(date_texte, texte_diffusion):
    """Transforme les dates textuelles (ex: Mardi 24 mars) en objet datetime"""
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
    # Gestion basique du passage à l'année suivante
    if mois < mois_actuel and mois_actuel > 10:
        annee_actuelle += 1

    return datetime.datetime(annee_actuelle, mois, jour, heure, minute, tzinfo=fuseau)

def evenements_se_chevauchent(event1, event2):
    """Vérifie si deux événements se chevauchent dans le temps."""
    # On détermine les débuts et fins (en gérant le cas où duration est défini au lieu de end)
    debut1 = event1.begin
    fin1 = event1.end if event1.end else debut1 + event1.duration
    
    debut2 = event2.begin
    fin2 = event2.end if event2.end else debut2 + event2.duration
    
    # Condition mathématique de chevauchement de deux intervalles
    return debut1 < fin2 and fin1 > debut2

def est_en_conflit_avec_api(nouvel_event, liste_events_api):
    """Vérifie si le nouvel événement chevauche au moins un événement de l'API."""
    for api_event in liste_events_api:
        if evenements_se_chevauchent(nouvel_event, api_event):
            return True
    return False


# ==========================================
# RÉCUPÉRATION DES DONNÉES
# ==========================================

def recuperer_evenements_rtbf_api(calendrier):
    """Étape 1 : Récupère les diffusions RTBF via leur API. Retourne aussi la liste des événements pour le check."""
    print("\n[Étape 1] Appel du widget Cyclisme RTBF (API)...")
    compteur = 0
    liste_events_api = []

    try:
        r = requests.get(WIDGET_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get('data', {}).get('content', [])

        if not items:
            print("  Aucun direct RTBF listé pour le moment via l'API.")
            return 0, []

        for item in items:
            title = item.get('title', 'Direct Cyclisme').strip()
            subtitle = item.get('subtitle', '').strip()
            start_str = item.get('scheduledFrom')
            end_str = item.get('scheduledTo')

            if start_str and end_str and "On connait nos classiques" not in title:
                e = Event()
                e.name = f"🚴 [RTBF] {title}"
                if subtitle:
                    e.name += f" - {subtitle}"

                e.begin = dateutil.parser.parse(start_str)
                e.end = dateutil.parser.parse(end_str)

                path = item.get('path')
                e.url = f"https://auvio.rtbf.be{path}" if path else "https://auvio.rtbf.be/direct"

                label = item.get('label', '')
                channel = item.get('channelLabel', 'RTBF')
                e.description = f"{label} sur {channel}.\nLien : {e.url}"
                e.location = channel

                calendrier.events.add(e)
                liste_events_api.append(e)
                compteur += 1

                debut_local = e.begin.astimezone(ZoneInfo("Europe/Brussels"))
                fin_local = e.end.astimezone(ZoneInfo("Europe/Brussels"))
                print(f"  Ajouté (API) : {e.name} | {debut_local.strftime('%d/%m de %H:%M')} à {fin_local.strftime('%H:%M')}")

    except Exception as e:
        print(f"  Erreur RTBF API : {e}")

    return compteur, liste_events_api


def recuperer_evenements_cyclismerevue(calendrier, liste_events_api):
    """Étapes 2 & 3 : Récupère le scraping. Ajoute RTBF si pas de conflit, ajoute RTL dans tous les cas."""
    print("\n[Étapes 2 & 3] Recherche des courses sur le programme TV web...")
    url = "https://cyclismerevue.be/programme-tv-cyclisme/"
    compteur_rtl = 0
    compteur_rtbf = 0

    try:
        reponse = requests.get(url, timeout=10)
        reponse.raise_for_status()
        soup = BeautifulSoup(reponse.text, 'html.parser')

        for li in soup.find_all('li'):
            texte_diffusion = li.get_text(strip=True)
            texte_upper = texte_diffusion.upper()
            
            # Détection de la chaîne
            est_rtl = 'RTL' in texte_upper
            est_rtbf = 'RTBF' in texte_upper or 'TIPIK' in texte_upper or 'LA UNE' in texte_upper

            if est_rtl or est_rtbf:
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
                        date_debut = extraire_date_heure(date_texte, texte_diffusion)

                        diffuseur = "RTL" if est_rtl else "RTBF"
                        evenement = Event()
                        evenement.name = f"🚴‍♂️ [{diffuseur}] {course_nom}"
                        evenement.begin = date_debut
                        evenement.duration = datetime.timedelta(hours=2, minutes=30)
                        evenement.description = f"Diffusion : {texte_diffusion}\nSource : {url}"
                        evenement.location = diffuseur

                        # RÈGLE 3 : RTL s'ajoute toujours
                        if est_rtl:
                            calendrier.events.add(evenement)
                            compteur_rtl += 1
                            print(f"  RTL - Ajouté : {course_nom} | {date_debut.strftime('%d/%m à %H:%M')}")
                        
                        # RÈGLE 2 : RTBF s'ajoute SEULEMENT s'il n'y a pas de conflit avec l'API
                        elif est_rtbf:
                            if not est_en_conflit_avec_api(evenement, liste_events_api):
                                calendrier.events.add(evenement)
                                compteur_rtbf += 1
                                print(f"  RTBF - Ajouté : {course_nom} | {date_debut.strftime('%d/%m à %H:%M')}")
                            else:
                                print(f"  RTBF - Ignoré : {course_nom} | {date_debut.strftime('%d/%m à %H:%M')}")

    except Exception as e:
        print(f"  Erreur Scraping Web : {e}")

    return compteur_rtl, compteur_rtbf


# ==========================================
# LANCEMENT PRINCIPAL
# ==========================================

def generer_calendrier_global():
    calendrier = Calendar()

    print("=== GÉNÉRATION DU CALENDRIER CYCLISTE BELGE ===")

    # 1. On peuple avec l'API RTBF et on garde ces événements en mémoire
    total_rtbf_api, liste_events_api = recuperer_evenements_rtbf_api(calendrier)

    # 2 & 3. On peuple avec le scraping (RTBF de secours + RTL)
    total_rtl_scraping, total_rtbf_scraping = recuperer_evenements_cyclismerevue(calendrier, liste_events_api)

    total_courses = total_rtbf_api + total_rtl_scraping + total_rtbf_scraping

    # Sauvegarde
    if total_courses > 0:
        nom_fichier = "rtbf_cyclisme_final.ics"
        with open(nom_fichier, 'w', encoding='utf-8') as f:
            f.writelines(calendrier.serialize())

        print("\n" + "=" * 65)
        print(f"SUCCÈS ! Fichier '{nom_fichier}' généré.")
        print(f"Bilan :")
        print(f"  - RTBF via API     : {total_rtbf_api} course(s)")
        print(f"  - RTBF via Web     : {total_rtbf_scraping} course(s) ajoutée(s) en complément")
        print(f"  - RTL via Web      : {total_rtl_scraping} course(s)")
        print(f"  TOTAL              : {total_courses} événements.")
        print("-> Importez ce fichier dans Google Agenda, Outlook ou Apple Calendar.")
        print("=" * 65 + "\n")
    else:
        print("\nAucune course n'a été trouvée sur aucune des chaînes. Le fichier n'a pas été créé.")


if __name__ == "__main__":
    generer_calendrier_global()