TEAM_NAMES_RU = {
    'Arsenal': 'Арсенал', 'Aston Villa': 'Астон Вилла', 'Atalanta': 'Аталанта', 'Athletic Club': 'Атлетик Бильбао',
    'Atletico Madrid': 'Атлетико Мадрид', 'Atlético Madrid': 'Атлетико Мадрид', 'Barcelona': 'Барселона',
    'Bayer Leverkusen': 'Байер', 'Bayern Munich': 'Бавария', 'Bayern München': 'Бавария', 'Benfica': 'Бенфика',
    'Bodo/Glimt': 'Будё-Глимт', 'Bodø/Glimt': 'Будё-Глимт', 'Borussia Dortmund': 'Боруссия Дортмунд',
    'Chelsea': 'Челси', 'Club Brugge KV': 'Брюгге', 'Club Brugge': 'Брюгге', 'Copenhagen': 'Копенгаген',
    'FC Copenhagen': 'Копенгаген', 'Eintracht Frankfurt': 'Айнтрахт Франкфурт', 'Galatasaray': 'Галатасарай',
    'Inter': 'Интер', 'Inter Milan': 'Интер', 'Juventus': 'Ювентус', 'Liverpool': 'Ливерпуль',
    'Manchester City': 'Манчестер Сити', 'Marseille': 'Марсель', 'Monaco': 'Монако', 'Napoli': 'Наполи',
    'Newcastle': 'Ньюкасл', 'Newcastle United': 'Ньюкасл', 'Olympiacos': 'Олимпиакос',
    'Paris Saint Germain': 'Пари Сен-Жермен', 'Paris Saint-Germain': 'Пари Сен-Жермен', 'PSG': 'Пари Сен-Жермен',
    'PSV Eindhoven': 'ПСВ', 'Real Madrid': 'Реал Мадрид', 'Slavia Praha': 'Славия Прага', 'Slavia Prague': 'Славия Прага',
    'Sporting CP': 'Спортинг', 'Sporting Lisbon': 'Спортинг', 'Tottenham': 'Тоттенхэм', 'Tottenham Hotspur': 'Тоттенхэм',
    'Villarreal': 'Вильярреал', 'Ajax': 'Аякс', 'Feyenoord': 'Фейеноорд', 'Celtic': 'Селтик',
    'Rangers': 'Рейнджерс', 'Fenerbahce': 'Фенербахче', 'Fenerbahçe': 'Фенербахче', 'Nice': 'Ницца',
    'Feyenoord Rotterdam': 'Фейеноорд', 'Red Bull Salzburg': 'Зальцбург', 'RB Salzburg': 'Зальцбург',
    'Sturm Graz': 'Штурм', 'Red Star Belgrade': 'Црвена Звезда', 'Crvena Zvezda': 'Црвена Звезда',
    'Dynamo Kyiv': 'Динамо Киев', 'Dynamo Kiev': 'Динамо Киев', 'Shakhtar Donetsk': 'Шахтёр Донецк',
    'Qarabag': 'Карабах', 'Qarabağ': 'Карабах', 'Pafos': 'Пафос', 'Kairat Almaty': 'Кайрат',
    'AEK Athens FC':'АЕК Афины','AEK Athens':'АЕК Афины','LASK Linz':'ЛАСК','LASK':'ЛАСК',
}

API_FOOTBALL_TEAM_IDS = {
    'Arsenal':42,'Aston Villa':66,'Atalanta':499,'Athletic Club':531,'Atletico Madrid':530,'Atlético Madrid':530,
    'Barcelona':529,'Bayer Leverkusen':168,'Bayern Munich':157,'Bayern München':157,'Benfica':211,
    'Borussia Dortmund':165,'Chelsea':49,'Club Brugge KV':569,'Club Brugge':569,'Eintracht Frankfurt':169,
    'Galatasaray':645,'Inter':505,'Inter Milan':505,'Juventus':496,'Liverpool':40,'Manchester City':50,
    'Marseille':81,'Monaco':91,'Napoli':492,'Newcastle':34,'Newcastle United':34,'Olympiacos':553,
    'Paris Saint Germain':85,'Paris Saint-Germain':85,'PSG':85,'PSV Eindhoven':197,'Real Madrid':541,
    'Sporting CP':228,'Sporting Lisbon':228,'Tottenham':47,'Tottenham Hotspur':47,'Villarreal':533,
    'Ajax':194,'Celtic':247,'Rangers':257,'Fenerbahce':611,'Fenerbahçe':611,'Nice':84,
    'Red Bull Salzburg':571,'RB Salzburg':571,'Red Star Belgrade':598,'Crvena Zvezda':598,
    'Dynamo Kyiv':572,'Dynamo Kiev':572,'Shakhtar Donetsk':550,'Qarabag':556,'Qarabağ':556,
}

def normalize_team_name(value: str | None) -> str:
    if not value:return ''
    return ' '.join(value.lower().replace('fc',' ').replace('cf',' ').replace('fk',' ').replace('afc',' ').replace('.',' ').replace('-',' ').replace("'",'').replace('’','').split())

def team_name_ru(name: str | None) -> str | None:
    if not name:return name
    return TEAM_NAMES_RU.get(name,name)

def fallback_team_logo(name: str | None) -> str | None:
    if not name:return None
    team_id=API_FOOTBALL_TEAM_IDS.get(name)
    if team_id is None:return None
    return f'/api/team-logo/{team_id}'

def team_logo_url(name: str | None, stored_logo: str | None) -> str | None:
    proxied=fallback_team_logo(name)
    return proxied or stored_logo

ROUND_NAMES_RU = {
    'League phase':'Этап лиги','Knockout phase play-offs':'Стыковые матчи','Round of 16':'1/8 финала',
    'Quarter-finals':'1/4 финала','Semi-finals':'1/2 финала','Final':'Финал',
}

def round_name_ru(label: str | None) -> str | None:
    if not label:return label
    value=label
    for en,ru in ROUND_NAMES_RU.items():value=value.replace(en,ru)
    return value.replace('Matchday ','Тур ').replace('Leg ','Матч ')
