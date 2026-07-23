"""Курируемый сид жанров (SPEC-КАТАЛОГ §1) на базе MusicBrainz genre list.

Структура: {топ-уровень: [дети]}. Ребёнок может сам быть словарём — третий
уровень («Электроника → Phonk → Drift Phonk»). Slug строится из имени.
Сид идемпотентен — повторный запуск ничего не дублирует (uq по slug).
"""

GENRE_TREE: dict[str, list] = {
    "Поп": [
        "Dance Pop", "Synth-pop", "Electropop", "Dream Pop", "Indie Pop",
        "Art Pop", "Chamber Pop", "Power Pop", "Teen Pop", "Bubblegum Pop",
        "K-pop", "J-pop", "C-pop", "Europop", "Latin Pop", "Hyperpop",
        "Bedroom Pop", "Sophisti-pop", "City Pop", "Baroque Pop",
        "Русская поп-музыка", "Ретро-поп 80-х", "Диско",
    ],
    "Хип-хоп": [
        "Rap", "Trap", "Drill", "Boom Bap", "Cloud Rap", "Mumble Rap",
        "Gangsta Rap", "Conscious Hip Hop", "Alternative Hip Hop",
        "East Coast Hip Hop", "West Coast Hip Hop", "Southern Hip Hop",
        "UK Hip Hop", "Grime", "Русский рэп", "Русский клауд-рэп",
        "Latin Trap", "Emo Rap", "Rage", "Plugg", "Pluggnb", "Hyphy",
        "Crunk", "Snap", "Horrorcore", "Chopped and Screwed", "Lo-fi Hip Hop",
        "Jazz Rap", "Trap Metal", "Phonk Rap",
    ],
    "Электроника": [
        {"House": [
            "Deep House", "Tech House", "Progressive House", "Electro House",
            "Future House", "Tropical House", "Acid House", "Bass House",
            "Slap House", "Afro House", "Melodic House",
        ]},
        {"Techno": [
            "Melodic Techno", "Minimal Techno", "Acid Techno", "Hard Techno",
            "Detroit Techno", "Industrial Techno",
        ]},
        {"Trance": [
            "Progressive Trance", "Uplifting Trance", "Psytrance", "Goa Trance",
            "Vocal Trance", "Hard Trance",
        ]},
        {"Drum and Bass": [
            "Liquid Funk", "Neurofunk", "Jump Up", "Jungle", "Breakcore",
        ]},
        {"Dubstep": ["Brostep", "Riddim", "Melodic Dubstep", "Future Riddim"]},
        {"Phonk": ["Drift Phonk", "House Phonk", "Brazilian Phonk", "Aggressive Phonk"]},
        {"Hardcore": ["Gabber", "Happy Hardcore", "Frenchcore", "Speedcore", "Hardstyle"]},
        "EDM", "Big Room", "Electro", "Breakbeat", "UK Garage", "2-step",
        "Future Bass", "Trap EDM", "Moombahton", "Glitch Hop", "Midtempo Bass",
        "IDM", "Ambient", "Downtempo", "Chillout", "Trip Hop", "Chillwave",
        "Synthwave", "Vaporwave", "Retrowave", "Darkwave", "Witch House",
        "Eurodance", "Hands Up", "Italo Disco", "Nu Disco", "French House",
        "Lo-fi", "Hardbass", "Jersey Club", "Footwork", "Wave", "Dungeon Synth",
    ],
    "Рок": [
        "Classic Rock", "Hard Rock", "Alternative Rock", "Indie Rock",
        "Punk Rock", "Pop Punk", "Post-punk", "Garage Rock", "Psychedelic Rock",
        "Progressive Rock", "Art Rock", "Glam Rock", "Grunge", "Post-grunge",
        "Britpop", "Shoegaze", "Post-rock", "Math Rock", "Emo", "Midwest Emo",
        "Screamo", "Ska Punk", "Surf Rock", "Rockabilly", "Blues Rock",
        "Southern Rock", "Stoner Rock", "Noise Rock", "Gothic Rock",
        "New Wave", "Русский рок", "Folk Rock", "Soft Rock", "Pub Rock",
    ],
    "Метал": [
        "Heavy Metal", "Thrash Metal", "Death Metal", "Black Metal",
        "Doom Metal", "Power Metal", "Progressive Metal", "Symphonic Metal",
        "Folk Metal", "Nu Metal", "Metalcore", "Deathcore", "Djent",
        "Groove Metal", "Industrial Metal", "Gothic Metal", "Sludge Metal",
        "Speed Metal", "Melodic Death Metal", "Alternative Metal",
    ],
    "R&B и соул": [
        "Contemporary R&B", "Neo Soul", "Soul", "Funk", "Motown",
        "Quiet Storm", "New Jack Swing", "Alternative R&B", "Afrobeats R&B",
        "Gospel", "Doo-wop", "G-funk",
    ],
    "Джаз": [
        "Smooth Jazz", "Bebop", "Swing", "Cool Jazz", "Free Jazz",
        "Jazz Fusion", "Acid Jazz", "Nu Jazz", "Vocal Jazz", "Big Band",
        "Bossa Nova", "Latin Jazz", "Gypsy Jazz",
    ],
    "Классика": [
        "Барокко", "Классицизм", "Романтизм", "Опера", "Симфоническая музыка",
        "Камерная музыка", "Фортепианная музыка", "Современная классика",
        "Неоклассика", "Саундтреки",
    ],
    "Фолк и кантри": [
        "Folk", "Indie Folk", "Americana", "Country", "Country Pop",
        "Bluegrass", "Celtic", "Русский фолк", "Авторская песня", "Шансон",
        "Bardcore", "Sea Shanty",
    ],
    "Блюз": ["Delta Blues", "Chicago Blues", "Electric Blues", "Country Blues"],
    "Регги и даб": [
        "Reggae", "Dancehall", "Dub", "Ska", "Rocksteady", "Reggaeton",
        "Ragga", "Lovers Rock",
    ],
    "Латино": [
        "Salsa", "Bachata", "Cumbia", "Merengue", "Tango", "Flamenco",
        "Bossa Nova Latino", "Corridos", "Corridos Tumbados", "Banda",
        "Mariachi", "Brazilian Funk", "Axé", "Forró",
    ],
    "Мировая музыка": [
        "Afrobeats", "Amapiano", "Highlife", "Afro Fusion", "K-hip hop",
        "J-rock", "Anime", "Bollywood", "Indian Pop", "Bhangra",
        "Arabic Pop", "Türkçe Pop", "Французский шансон", "Средиземноморская",
        "Кавказская музыка", "Этника",
    ],
    "Инструментальная": [
        "Минусовки", "Биты", "Type Beats", "Инструментальный хип-хоп",
        "Гитарная инструментальная", "Эпическая музыка", "Медитация",
        "Звуки природы", "White Noise",
    ],
    "Настроение и эпохи": [
        "80-е", "90-е", "2000-е", "2010-е", "Хиты", "Лето", "Для сна",
        "Для тренировок", "Для учёбы", "Грустное", "Романтика", "Вечеринка",
        "В машину", "Новогоднее",
    ],
    "Детская": ["Детские песни", "Колыбельные", "Из мультфильмов"],
    "Разговорные": ["Подкасты", "Аудиокниги", "Стендап", "ASMR"],
}
