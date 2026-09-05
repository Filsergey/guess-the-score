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
}

def team_name_ru(name: str | None) -> str | None:
    if not name:
        return name
    return TEAM_NAMES_RU.get(name, name)

ROUND_NAMES_RU = {
    'League phase': 'Этап лиги', 'Knockout phase play-offs': 'Стыковые матчи', 'Round of 16': '1/8 финала',
    'Quarter-finals': '1/4 финала', 'Semi-finals': '1/2 финала', 'Final': 'Финал',
}

def round_name_ru(label: str | None) -> str | None:
    if not label:
        return label
    value = label
    for en, ru in ROUND_NAMES_RU.items():
        value = value.replace(en, ru)
    value = value.replace('Matchday ', 'Тур ').replace('Leg ', 'Матч ')
    return value
