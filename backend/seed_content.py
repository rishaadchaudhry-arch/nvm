"""Starter content for Yatra.

Everything here is hand-written starter content (not AI generated). It is drawn from
well-documented history but should be fact-checked by the content team before launch.
New regions, areas and points of interest can be added later through the admin
content endpoints without any code change.
"""

SEED_VERSION = 2  # bump when starter content changes

W = "https://commons.wikimedia.org/wiki/Special:FilePath/"
U = "https://images.unsplash.com/"

# Ordered era keys used by the time slider. An area lists the subset it has content for.
ERAS = {
    "1650s": "1600s · Mughal city",
    "1700s": "1700–1850 · Late Mughal",
    "1857": "1857 · The Revolt",
    "1900s": "1860–1940 · British Delhi",
    "1947": "1947 · Partition",
    "1970s": "1970s · Old Delhi bustle",
    "today": "Today",
}

REGIONS = [
    {
        "slug": "delhi",
        "name": "Delhi",
        "kind": "state",
        "cover_image": U + "photo-1713729991304-d0b6c328560e?fm=jpg&q=80&w=1600",
        "summary": "A city rebuilt at least seven times, from Sultanate forts to Shah Jahan's walled Shahjahanabad and Lutyens' New Delhi.",
        "eras": [
            {"key": "1650s", "title": "Shahjahanabad is founded", "description": "Shah Jahan moves the Mughal capital from Agra and builds a walled city with the Red Fort (completed 1648), Jama Masjid and Chandni Chowk at its heart."},
            {"key": "1700s", "title": "A capital under attack", "description": "Nadir Shah sacks Delhi in 1739 and carries away the Peacock Throne. Marathas, Rohillas and Afghans contest the weakened city for decades."},
            {"key": "1857", "title": "The Revolt", "description": "Rebel soldiers proclaim Bahadur Shah Zafar emperor. After a four-month siege the British retake Delhi and exile the last Mughal emperor to Rangoon."},
            {"key": "1900s", "title": "Capital of British India", "description": "At the 1911 Delhi Durbar, George V announces the capital will move from Calcutta. New Delhi is inaugurated in 1931."},
            {"key": "1947", "title": "Independence and Partition", "description": "Delhi becomes the capital of independent India and absorbs hundreds of thousands of refugees from West Punjab, reshaping its neighbourhoods."},
            {"key": "today", "title": "National Capital Territory", "description": "Home to over 20 million people, Delhi layers metro lines and glass towers over a thousand years of monuments."},
        ],
    },
    {"slug": "uttar-pradesh", "name": "Uttar Pradesh", "kind": "state", "cover_image": U + "photo-1587135941948-670b381f08ce?fm=jpg&q=80&w=1600", "summary": "", "eras": []},
    {"slug": "karnataka", "name": "Karnataka", "kind": "state", "cover_image": U + "photo-1696239109250-a83577abcbeb?fm=jpg&q=80&w=1600", "summary": "", "eras": []},
    {"slug": "odisha", "name": "Odisha", "kind": "state", "cover_image": U + "photo-1639980290886-6bdd61c7582b?fm=jpg&q=80&w=1600", "summary": "", "eras": []},
    {"slug": "madhya-pradesh", "name": "Madhya Pradesh", "kind": "state", "cover_image": U + "photo-1672215055915-e6143dc70e6a?fm=jpg&q=80&w=1600", "summary": "", "eras": []},
    {"slug": "punjab", "name": "Punjab", "kind": "state", "cover_image": W + "The_Golden_Temple_of_Amrithsar_7.jpg?width=1600", "summary": "", "eras": []},
]

AREAS = [
    {
        "slug": "chandni-chowk",
        "region_slug": "delhi",
        "name": "Chandni Chowk",
        "lat": 28.6562,
        "lng": 77.2300,
        "radius_m": 1500,
        "cover_image": W + "Gurudwara_Sis_Ganj_Sahib.jpg?width=1600",
        "summary": "Laid out around 1650 by Jahanara Begum, Shah Jahan's daughter, as the grand avenue of Shahjahanabad, running from the Red Fort to Fatehpuri Masjid.",
        "era_keys": ["1650s", "1700s", "1857", "1900s", "1947", "1970s", "today"],
        "eras": [
            {"key": "1650s", "title": "The moonlit square", "description": "A canal, the Nahr-i-Bahisht, ran down the middle of the street. A pool near the centre reflected the moon, which is the most common explanation for the name Chandni Chowk."},
            {"key": "1700s", "title": "Massacre of 1739", "description": "Nadir Shah's troops killed thousands of residents here in a single day while he watched from the Sunehri Masjid."},
            {"key": "1857", "title": "Battleground", "description": "During and after the Revolt the street saw fighting, looting and public executions near the Kotwali. Large parts of the old city were cleared by the British."},
            {"key": "1900s", "title": "Trams and a clock tower", "description": "The canal was covered over, a Town Hall and clock tower rose mid-street, and electric trams ran along Chandni Chowk from 1908 until 1963."},
            {"key": "1947", "title": "Refugee traders", "description": "Families arriving from Lahore and Rawalpindi set up shops in the lanes, many of which their grandchildren still run."},
            {"key": "1970s", "title": "Wholesale capital", "description": "Cycle rickshaws, handcarts and wholesale markets for cloth, spices, silver and electricals packed the street from dawn to dusk."},
            {"key": "today", "title": "A pedestrian avenue again", "description": "A redevelopment completed in 2021 made the stretch from the Red Fort to Fatehpuri largely free of motor traffic by day, with red sandstone paving."},
        ],
    },
    {"slug": "red-fort", "region_slug": "delhi", "name": "Red Fort", "lat": 28.6562, "lng": 77.2410, "radius_m": 600, "cover_image": U + "photo-1713729991304-d0b6c328560e?fm=jpg&q=80&w=1600", "summary": "", "era_keys": [], "eras": []},
    {"slug": "qutub-minar", "region_slug": "delhi", "name": "Qutub Minar", "lat": 28.5245, "lng": 77.1855, "radius_m": 600, "cover_image": W + "Qutb_Minar_2011.jpg?width=1600", "summary": "", "era_keys": [], "eras": []},
    {"slug": "taj-mahal", "region_slug": "uttar-pradesh", "name": "Taj Mahal", "lat": 27.1751, "lng": 78.0421, "radius_m": 800, "cover_image": U + "photo-1587135941948-670b381f08ce?fm=jpg&q=80&w=1600", "summary": "", "era_keys": [], "eras": []},
    {"slug": "hampi", "region_slug": "karnataka", "name": "Hampi", "lat": 15.3350, "lng": 76.4600, "radius_m": 3000, "cover_image": U + "photo-1696239109250-a83577abcbeb?fm=jpg&q=80&w=1600", "summary": "", "era_keys": [], "eras": []},
    {"slug": "mysore-palace", "region_slug": "karnataka", "name": "Mysore Palace", "lat": 12.3051, "lng": 76.6551, "radius_m": 600, "cover_image": U + "photo-1764858147489-47a546c6e8ca?fm=jpg&q=80&w=1600", "summary": "", "era_keys": [], "eras": []},
    {"slug": "konark", "region_slug": "odisha", "name": "Konark", "lat": 19.8876, "lng": 86.0945, "radius_m": 800, "cover_image": U + "photo-1639980290886-6bdd61c7582b?fm=jpg&q=80&w=1600", "summary": "", "era_keys": [], "eras": []},
    {"slug": "khajuraho", "region_slug": "madhya-pradesh", "name": "Khajuraho", "lat": 24.8318, "lng": 79.9199, "radius_m": 1500, "cover_image": U + "photo-1672215055915-e6143dc70e6a?fm=jpg&q=80&w=1600", "summary": "", "era_keys": [], "eras": []},
    {"slug": "amritsar-golden-temple", "region_slug": "punjab", "name": "Golden Temple, Amritsar", "lat": 31.6200, "lng": 74.8765, "radius_m": 800, "cover_image": W + "The_Golden_Temple_of_Amrithsar_7.jpg?width=1600", "summary": "", "era_keys": [], "eras": []},
]


def _e(key, title, description):
    return {"key": key, "title": title, "description": description}


POIS = [
    {
        "slug": "lahori-gate", "area_slug": "chandni-chowk", "name": "Lahori Gate, Red Fort", "category": "Monument",
        "lat": 28.6563, "lng": 77.2377, "image": U + "photo-1713729991304-d0b6c328560e?fm=jpg&q=80&w=1200",
        "eras": [
            _e("1650s", "Gateway to the emperor", "The Red Fort was completed in 1648. Its main gate faces west towards Lahore, looking straight down Chandni Chowk."),
            _e("1857", "The fort falls", "British troops entered the fort in September 1857. Bahadur Shah Zafar was tried in its halls and exiled."),
            _e("1947", "The first flag", "Jawaharlal Nehru raised the Indian flag here on 16 August 1947, beginning a tradition that continues every Independence Day."),
            _e("today", "World Heritage Site", "A UNESCO World Heritage Site since 2007. The Prime Minister addresses the nation from these ramparts every 15 August."),
        ],
    },
    {
        "slug": "jain-lal-mandir", "area_slug": "chandni-chowk", "name": "Digambar Jain Lal Mandir", "category": "Temple",
        "lat": 28.6560, "lng": 77.2348, "image": W + "Sri_Digambar_Jain_Lal_Mandir.jpg?width=800",
        "eras": [
            _e("1650s", "A temple for Jain soldiers", "Traditionally dated to 1656, the oldest Jain temple in Delhi began as a place of worship for Jain officers in the Mughal army."),
            _e("1900s", "The bird hospital", "A charity hospital for birds was set up in the temple complex in the early 20th century and still treats injured pigeons and sparrows."),
            _e("today", "Red sandstone landmark", "The red sandstone facade gives the temple its name, Lal Mandir, the red temple."),
        ],
    },
    {
        "slug": "gauri-shankar-temple", "area_slug": "chandni-chowk", "name": "Gauri Shankar Temple", "category": "Temple",
        "lat": 28.6561, "lng": 77.2338, "image": W + "Gauri_Shankar_Temple_Pics_01.jpg?width=800",
        "eras": [
            _e("1700s", "A soldier's vow", "Built around 1761 by Apa Gangadhar, a Maratha soldier, who is said to have vowed to build a Shiva temple if he survived battle."),
            _e("today", "Mondays and Shivratri", "Long queues form on Mondays and during Shivratri, when devotees offer milk and bel leaves to the lingam."),
        ],
    },
    {
        "slug": "central-baptist-church", "area_slug": "chandni-chowk", "name": "Central Baptist Church", "category": "Church",
        "lat": 28.6560, "lng": 77.2323, "image": W + "Central_Baptist_Church,_Delhi_04.jpg?width=800",
        "eras": [
            _e("1700s", "A church on a Mughal street", "Founded by the Baptist Missionary Society in the early 1800s, it is one of the oldest churches in north India."),
            _e("1857", "Caught in the Revolt", "The mission was attacked during the 1857 uprising and its pastor killed."),
            _e("today", "Sunday services in Hindi", "The church still holds services, a short walk from temples, gurdwaras and mosques on the same street."),
        ],
    },
    {
        "slug": "bhagirath-palace", "area_slug": "chandni-chowk", "name": "Bhagirath Palace", "category": "Market",
        "lat": 28.6577, "lng": 77.2316, "image": "",
        "eras": [
            _e("1700s", "Begum Samru's mansion", "Built in the early 1800s for Begum Samru, a dancer who rose to rule the principality of Sardhana and lead her own army."),
            _e("1857", "The bank that was looted", "By then the building housed the Delhi Bank. Rebels attacked it in May 1857 and killed the manager's family."),
            _e("1970s", "Electricals bazaar", "The palace was swallowed by shops and became one of Asia's biggest wholesale markets for electrical goods."),
            _e("today", "Look up", "Above the switchboards and cable reels you can still see the old colonnade of Begum Samru's palace."),
        ],
    },
    {
        "slug": "gurudwara-sis-ganj", "area_slug": "chandni-chowk", "name": "Gurudwara Sis Ganj Sahib", "category": "Gurudwara",
        "lat": 28.6560, "lng": 77.2312, "image": W + "Gurudwara_Sis_Ganj_Sahib.jpg?width=800",
        "eras": [
            _e("1650s", "Martyrdom of Guru Tegh Bahadur", "In 1675 the ninth Sikh Guru was executed here on Aurangzeb's orders. His follower Bhai Jaita carried his head to Anandpur Sahib."),
            _e("1700s", "The shrine is built", "In 1783 the Sikh general Baghel Singh, whose army entered Delhi, built a shrine at the site."),
            _e("today", "Langar for all", "The gurudwara serves free meals to thousands of visitors every day. The trunk of the tree under which the Guru was martyred is preserved inside."),
        ],
    },
    {
        "slug": "sunehri-masjid", "area_slug": "chandni-chowk", "name": "Sunehri Masjid", "category": "Mosque",
        "lat": 28.6561, "lng": 77.2304, "image": W + "Sunehri_Masjid,_Chandni_Chowk,_Delhi.jpg?width=800",
        "eras": [
            _e("1700s", "Where Nadir Shah sat", "Built in 1721 by the noble Roshan-ud-Daula. On 11 March 1739 Nadir Shah watched from its roof as his troops massacred the city."),
            _e("today", "Easy to miss", "Its once-gilded domes now sit squeezed between shops next to the Kotwali and Gurudwara Sis Ganj."),
        ],
    },
    {
        "slug": "paranthe-wali-gali", "area_slug": "chandni-chowk", "name": "Paranthe Wali Gali", "category": "Food",
        "lat": 28.6553, "lng": 77.2297, "image": W + "Gali_Paranthe_Wali.jpg?width=800",
        "eras": [
            _e("1900s", "Lane of fried bread", "Paratha shops began opening in this lane in the 1870s. Several are still run by descendants of the founding families."),
            _e("1947", "Famous customers", "Shop owners proudly display photographs of visits by national leaders in the years after Independence."),
            _e("today", "Still frying", "Stuffed parathas, deep-fried in ghee, are served with tamarind chutney and potato curry in a lane barely two people wide."),
        ],
    },
    {
        "slug": "town-hall", "area_slug": "chandni-chowk", "name": "Town Hall & Clock Tower site", "category": "Civic",
        "lat": 28.6575, "lng": 77.2282, "image": W + "Delhi_Town_Hall.jpg?width=800",
        "eras": [
            _e("1650s", "Jahanara's garden", "Behind this spot lay Begum ka Bagh, a large garden laid out by Jahanara Begum."),
            _e("1900s", "Town Hall and Ghanta Ghar", "The British built a Town Hall in the 1860s and a clock tower in the middle of the street around 1870. The tower collapsed in 1951."),
            _e("today", "Empty council chambers", "Delhi's municipal corporation worked from the Town Hall until 2009. The building now stands largely unused."),
        ],
    },
    {
        "slug": "fatehpuri-masjid", "area_slug": "chandni-chowk", "name": "Fatehpuri Masjid", "category": "Mosque",
        "lat": 28.6568, "lng": 77.2226, "image": W + "Fatehpuri_Masjid_in_Delhi_19.jpg?width=800",
        "eras": [
            _e("1650s", "The other end of the avenue", "Built in 1650 by Fatehpuri Begum, one of Shah Jahan's wives, to close the western end of Chandni Chowk."),
            _e("1857", "Sold at auction", "After 1857 the British auctioned the mosque to a Hindu merchant. It was returned to the Muslim community in 1877."),
            _e("today", "Gateway to the spice market", "Its courtyard is a quiet pause before the crowds of Khari Baoli next door."),
        ],
    },
    {
        "slug": "khari-baoli", "area_slug": "chandni-chowk", "name": "Khari Baoli Spice Market", "category": "Market",
        "lat": 28.6575, "lng": 77.2209, "image": W + "36_-_Old_Delhi_Khari_Baoli.jpg?width=800",
        "eras": [
            _e("1650s", "The salty stepwell", "The street takes its name from a stepwell with brackish water, khari baoli, that once stood here."),
            _e("1970s", "Asia's spice wholesaler", "Porters carried sacks of chillies, turmeric and dry fruit through the lanes to traders from across north India."),
            _e("today", "Follow your nose", "Still Asia's largest wholesale spice market. Expect to sneeze as chilli dust drifts through Gadodia Market."),
        ],
    },
    {
        "slug": "jama-masjid", "area_slug": "chandni-chowk", "name": "Jama Masjid", "category": "Mosque",
        "lat": 28.6507, "lng": 77.2334, "image": W + "Jama_Masjid,_Delhi.jpg?width=800",
        "eras": [
            _e("1650s", "The emperor's mosque", "Built by Shah Jahan between 1650 and 1656. Its courtyard can hold around 25,000 worshippers."),
            _e("1857", "Occupied by troops", "After retaking Delhi the British stationed soldiers in the mosque and only returned it for worship in 1862."),
            _e("today", "Eid in Old Delhi", "On Eid the courtyard and the steps fill completely, and the lanes below turn into a night-long food market."),
        ],
    },
]
