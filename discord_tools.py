# JARVIS-DISCORD-TOOLS-v0.6.27-GIGAAM-ALIASES

import json
from assistant_identity import wake_aliases
import re
import urllib.error
import urllib.request


DISCORD_TOOLS_VERSION = "JARVIS-DISCORD-TOOLS-v0.6.28-RUSSIAN-ROULETTE"
BRIDGE_URL = "http://127.0.0.1:8765"


# ------------------------------------------------------------
# Состояние команды OFF.
#
# False / отсутствует:
#   следующий "оффни" = mute + deaf
#
# True:
#   следующий "оффни" = unmute + undeaf
#
# Сбрасывается после перезапуска JARVIS.
# ------------------------------------------------------------

OFF_STATE = {}


ALIASES = {
    "friday_vip": (
        # Именительный падеж («Пятница», «Пятничка») — это повторное
        # обращение к боту, а не цель наказания. Целью считаются только
        # недвусмысленные падежные формы.
        "пятницу", "пятнице", "пятницей",
        "пятничку", "пятничке",
    ),

    "mashonka": (
        "скеладум", "скеладума", "скеладуму", "скеладуме",
        "skeeladoom", "машонка", "машонку", "машонке",
    ),

    # Даня намеренно существует только как защищённая голосовая цель. Его
    # Discord ID не нужен: команда блокируется до обращения к Discord bridge.
    "danya_vip": (
        "даня", "даню", "дане", "дани", "даней",
        "данька", "даньку", "даньке", "даник", "данику",
        "данил", "данила", "данилу", "даниле",
    ),

    "anton": (
        "антон", "антона", "антону",
        "антончик", "антончика", "антончику",
        "тоха", "тоху", "тохе",
        "василенко", "василенка", "василенку", "василенке",
        "вазиленко", "вазиленка", "вазиленку", "вазиленке",
    ),

    "barashka": (
        "балыч", "балыча", "балычу",
        "денис балка", "денису балке",
        "балка", "балку", "балке", "балки", "балкой",
        "дэнчик", "денчик",
        "дэнчику", "денчику",
        "асфальтоукладчик",
        "асфальтоукладчика",
        "асфальтоукладчику",
    ),

    "bodya": (
        "бодя", "бодю", "боде",
        "богдан", "богдана", "богдану",
        "жук", "жука", "жуку", "жуке",
        "чурка", "чурку", "чурке",
        "мишаня", "мишане",
    ),

    "denisserguck": (
        "сердюк", "сердюка", "сердюку", "сердюке", "сердюком",
        "дэничка", "дэничку",
    ),

    "dima": (
        "дима", "диму", "диме",
        "димую",
        "зима", "зиму", "зиме",

        "дмитрий", "дмитрия", "дмитрию",

        "куколд", "куколда", "куколду",

        "кубышкин", "кубышкина", "кубышкину",

        "кубик", "кубика", "кубику",

        "пепельница", "пепельницу", "пепельнице",

        # Общее обращение одновременно к Диме и Егору.
        "мотобратик", "мотобратика", "мотобратику", "мотобратике",
        "мото братик", "мото братика", "мото братику", "мото брат",
        "мотобрат", "мотобрата", "мотобрату",
        "матобратик", "матобратика", "матобратику",
        "мата братик", "мото братик", "мотобратьик", "мотобратик",
    ),

    "jeka": (
        "жека", "жеку", "жеке",

        "евгений", "евгения", "евгению",

        "таран", "тарана", "тарану", "таране",
        "тарен", "тарена", "тарену", "тарене",

        "батя димы",
        "батю димы",
        "бате димы",

        "отец димы",
        "отца димы",
        "отцу димы",

        "спущёнка",
        "спущёнку",
        "спущёнке",

        "спущенка",
        "спущенку",
        "спущенке",
    ),

    "nazrik": (
        "назрик", "назрика", "назрику",
    ),

    "nazar": (
        "назар", "назара", "назару", "назаре",
        "тазар", "тазара", "тазару", "тазаре",
        "ванжа", "ванжу", "ванже",
        "ванжа", "ванжи", "ванжой",
    ),

    "egor": (
        "егор", "егора", "егору", "егоре",
        "егорка", "егорку", "егорке",
        "мотобратик", "мотобратика", "мотобратику", "мотобратике",
        "мото братик", "мото братика", "мото братику", "мото брат",
        "мотобрат", "мотобрата", "мотобрату",
        "матобратик", "матобратика", "матобратику",
        "мата братик", "мотобратьик", "мотобратик",
    ),

    "nastya": (
        "настя", "настю", "насте",
        "анастасия", "анастасию", "анастасии",
        "савченко", "савченка", "савченку", "савченке",
    ),

    "nikita": (
        "никита",
        "никиту",
        "никите",

        # Реальный вариант Vosk
        "никитин",

        "некит",
        "некита",
        "некиту",
        "неките",
        "текит", "текита", "текиту", "теките",

        "садовниченко",
        "садовникова",
        "садовников", "садовникову", "садовникове",
    ),

    "pushka": (
        "пушка", "пушку", "пушке", "пушки",

        "дарина", "дарину", "дарине", "дариной",

        "уродка", "уродку", "уродке",

        "яндекс карты",
        "яндекс карта",

        "карта", "карты", "карте",

        "трасса", "трассу", "трассе",

        "шлюха", "шлюху", "шлюхе",
    ),

    "viter": (
        "ветер", "ветра", "ветру",

        "илья", "илью", "илье",

        "илюха", "илюху", "илюхе",
    ),

    "lena": (
        "лена", "лену", "лене",
    ),
}

# One spoken person can intentionally expand to several Discord accounts.
ALIASES["dima_alt"] = ALIASES["dima"]
NIKITA_SHARED = (
    "никита", "никиту", "никите", "никиты", "никитой",
    "некит", "некита", "некиту", "неките", "неком",
)
ALIASES["nikita_braslavsky"] = NIKITA_SHARED + (
    "браславский", "браславского", "браславскому",
    "браславским", "браславском",
    "браславский", "брославский", "браславски",
)
# Generic «Никита» targets both people; Sadovnikov-specific aliases remain only
# on the original key and Braslavsky-specific aliases only on the second key.
ALIASES["nikita"] += NIKITA_SHARED
ALIASES["nikita_polish"] = NIKITA_SHARED + (
    "польский", "польского", "польскому", "польским", "польском", "польски",
    "польскый", "польсково", "польскава", "польскаму",
    "пойский", "пойского", "пойскому", "пойским", "пойском",
    "поисков", "поискова", "поискову", "поискове", "поискового", "поисковому",
    "поляк", "поляка", "поляку", "поляке", "поляком",
    "паляк", "паляка", "паляку", "паляке", "паляком",
    "навроцкий", "навроцкого", "навроцкому", "навроцким", "навроцком", "навроцки",
    "навротский", "навротского", "навротскому", "навротским", "навротском",
    "навороцкий", "навороцкого", "навороцкому", "навороцким", "навороцком",
    "сперма навроцкого", "сперму навроцкого", "сперме навроцкого", "спермы навроцкого",
    "сперма навротского", "сперму навротского", "сперме навротского", "спермы навротского",
    "сперма навороцкого", "сперму навороцкого", "сперме навороцкого", "спермы навороцкого",
)


# Просто "Денис" = оба Дениса.
NIKITA_SPECIFIC_ALIASES = {
    "nikita": (
        "садовниченко", "садовников", "садовникова", "садовникову", "садовникове",
        "садовниковым", "садовником", "садовникоф", "садовникаф",
    ),
    "nikita_braslavsky": (
        "браславский", "браславского", "браславскому", "браславским", "браславском",
        "брославский", "брославского", "браславски", "браслафский", "браслаского",
    ),
    "nikita_polish": (
        "польский", "польского", "польскому", "польским", "польском", "польски",
        "польскый", "польсково", "польскава", "польскаму",
        "пойский", "пойского", "пойскому", "пойским", "пойском",
        "поисков", "поискова", "поискову", "поискове", "поискового", "поисковому",
        "поляк", "поляка", "поляку", "поляке", "поляком",
        "паляк", "паляка", "паляку", "паляке", "паляком",
        "навроцкий", "навроцкого", "навроцкому", "навроцким", "навроцком", "навроцки",
        "навротский", "навротского", "навротскому", "навротским", "навротском",
        "навороцкий", "навороцкого", "навороцкому", "навороцким", "навороцком",
        "сперма навроцкого", "сперму навроцкого", "сперме навроцкого", "спермы навроцкого",
        "сперма навротского", "сперму навротского", "сперме навротского", "спермы навротского",
    ),
}


DENIS_SHARED = (
    "денис",
    "дениса",
    "денису",
    "денисе",
    "денисом",
    "ден",
    "дэн",
)


DISPLAY_NAMES_BY_CASE = {
    "nominative": {
        "friday_vip": "Пятница", "mashonka": "Skeeladoom", "danya_vip": "Даня",
        "anton": "Антон", "barashka": "Балыч", "bodya": "Бодя",
        "denisserguck": "Сердюк", "dima": "Дима", "dima_alt": "Дима",
        "jeka": "Жека", "egor": "Егор", "nastya": "Настя", "nazar": "Назар",
        "nazrik": "Назрик", "nikita": "Никита", "nikita_braslavsky": "Никита",
        "nikita_polish": "Никита Польский", "pushka": "Дарина",
        "viter": "Илья", "lena": "Лена",
    },
    "accusative": {
        "friday_vip": "Пятницу", "mashonka": "Skeeladoom", "danya_vip": "Даню",
        "anton": "Антона", "barashka": "Балыча", "bodya": "Бодю",
        "denisserguck": "Сердюка", "dima": "Диму", "dima_alt": "Диму",
        "jeka": "Жеку", "egor": "Егора", "nastya": "Настю", "nazar": "Назара",
        "nazrik": "Назрика", "nikita": "Никиту", "nikita_braslavsky": "Никиту",
        "nikita_polish": "Никиту Польского", "pushka": "Дарину",
        "viter": "Илью", "lena": "Лену",
    },
    "dative": {
        "friday_vip": "Пятнице", "mashonka": "Skeeladoom", "danya_vip": "Дане",
        "anton": "Антону", "barashka": "Балычу", "bodya": "Боде",
        "denisserguck": "Сердюку", "dima": "Диме", "dima_alt": "Диме",
        "jeka": "Жеке", "egor": "Егору", "nastya": "Насте", "nazar": "Назару",
        "nazrik": "Назрику", "nikita": "Никите", "nikita_braslavsky": "Никите",
        "nikita_polish": "Никите Польскому", "pushka": "Дарине",
        "viter": "Илье", "lena": "Лене",
    },
}

# Compatibility for code that only needs the old accusative labels.
DISPLAY_NAMES = DISPLAY_NAMES_BY_CASE["accusative"]

ACCOUNT_GROUPS = (
    frozenset(("dima", "dima_alt")),
    frozenset(("nikita", "nikita_braslavsky", "nikita_polish")),
)

PROTECTED_LOCAL_KEYS = frozenset(("danya_vip", "friday_vip"))
RETALIATION_PROTECTED_KEYS = frozenset(
    ("danya_vip", "friday_vip", "mashonka")
)
RETALIATION_ACTIONS = frozenset(
    ("disconnect", "mute", "deaf", "off_toggle", "full_disable")
)
VIP_IMMUNE_SPEAKER_KEYS = frozenset(("mashonka",))


# ------------------------------------------------------------
# ACTION ALIASES
# ------------------------------------------------------------

OFF_ALIASES = (
    # Нормальные варианты
    "оффни",
    "оффнуть",
    "оффнул",
    "офф",

    # Vosk может потерять вторую "ф"
    "офни",
    "офнуть",
    "офнул",

    # Англицизированное произношение
    "оффани",
    "офани",

    # Более длинные безопасные варианты
    "выруби полностью",
    "отключи полностью",
    "полностью выруби",
    "полностью отключи",

    "полный мут",
    "фулл мут",
    "фул мут",
)


FULL_DISABLE_ALIASES = (
    "выключи все", "отключи все", "выруби все",
    "все выключи", "все отключи", "все выруби",
    "выключи полностью", "отключи полностью", "выруби полностью",
    "полностью выключи", "полностью отключи", "полностью выруби",
    "выключи звук и микрофон", "отключи звук и микрофон",
    "выключи микрофон и звук", "отключи микрофон и звук",
    "замуть полностью", "замути полностью",
    "полностью замуть", "полностью замути",
    "полный мут", "дай полный мут",
    "отключи и микрофон и звук", "выключи и микрофон и звук",
)


FULL_RESTORE_ALIASES = (
    "размуть полностью",
    "размути полностью",
    "раз муть полностью",
    "раз мути полностью",
    "полностью размуть",
    "полностью размути",
    "полностью раз муть",
    "полностью раз мути",
    "полный размут",
    "полный раз мут",
    "фулл размут",
    "фул размут",
    "верни полностью",
    "полностью верни",
    "включи полностью",
    "полностью включи",
    "верни звук и микрофон",
    "включи звук и микрофон",
    "верни микрофон и звук",
    "включи микрофон и звук",
    "включи все",
    "все включи",
    "верни все",
    "все верни",
    "размуть все",
    "все размуть",
    "сними полный мут",
    "убери полный мут",
    "полностью размуть все",
    "верни и микрофон и звук",
)


MUTE_ALIASES = (
    "отключи микрофон",
    "выключи микрофон",

    "замуть",
    "замьють",
    "замьютить",

    "замути",
    "замут",
    "за муть",
    "за мути",
    "за мут",

    "мутни",
    "мьютни",
    "мут ни",
    "мьют ни",

    "дай мут",
)


UNMUTE_ALIASES = (
    "включи микрофон",
    "верни микрофон",

    # Реальный Vosk-вариант
    "подключи микрофон",

    "размуть",
    "размути",
    "размют",
    "размьют",
    "раз мут",
    "раз муть",
    "раз мути",
    "раз мьют",

    "сними мут",
    "убери мут",
    "сними мут с",
)


DEAF_ALIASES = (
    "отключи звук",
    "выключи звук",

    "заглуши",
    "оглуши",

    "задеф",
    "задэф",
    "за дэф",
    "за деф",

    "дефни",
    "дэфни",
    "деф ни",
    "дэф ни",
)


UNDEAF_ALIASES = (
    "включи звук",
    "подключи звук",

    "верни звук",
    "сними заглушение",
    "убери заглушение",

    "сними глуш",
    "разглуш",
    "раз глуш",
)


DISCONNECT_ALIASES = (
    # Common bounded Whisper distortions of «кикни».
    "кейкни",
    "кекни",
    "кигни",
    "кихни",
    "кижне",
    "кижни",
    "китни",
    "кипни",
    "кинь",
    "кини",
    "кликни",

    "кикни",
    "кикне",
    "кикну",
    "кикню",
    "кикны",
    "кикнуть",
    "кик ни",
    "кик не",
    "кик ну",
    "кик ню",
    "кик ны",

    "выкинь",
    "выкини",

    "вышвырни",

    "отключи от войса",
    "отключи из войса",

    "выкинь из войса",
    "кикни из войса",
)


# ------------------------------------------------------------
# TEXT
# ------------------------------------------------------------

# Whisper sometimes glues a short action to the following name when several
# people speak quickly: «за мутникиту», «мутдиму», «кикниназара».  Restrict
# recovery to known person stems so an arbitrary word cannot become a command.
ATTACHED_TARGET_STEM_RE = (
    r"(?:никит|некит|текит|дим|зим|дмитр|назар|тазар|назрик|егор|наст|анастас|"
    r"богдан|бод|дарин|пушк|антон|тох|денис|дэн|балк|сердюк|жек|евген|таран|"
    r"тарен|иль|илюх|ветер|дан|данил|скеладум|машонк|лен|браслав|польск|поляк|"
    r"паляк|навроц|наврот|навороц|мотобрат|матобрат)[а-я]*"
)


# Добровольная шуточная команда: отключить от голосового канала именно того,
# кто её произнёс. Полное совпадение защищает от срабатывания на обычный
# разговор со словом «убей». Несколько вариантов оставлены только для
# типичных ошибок распознавания короткой фразы.
SELF_DISCONNECT_RE = re.compile(
    r"^(?:(?:пятница|пятничка)\s+)?"
    r"(?:пожалуйста\s+)?(?:давай\s+)?"
    r"(?:убей|убейте|убить|убеи|у\s+бей)\s+"
    r"(?:меня|миня|мня)"
    r"(?:\s+(?:пожалуйста|из\s+войса|с\s+войса))?$",
    re.IGNORECASE,
)


GENOCIDE_ALIASES = (
    "геноцид", "геноцит", "генацид", "гинацид", "генасид",
    "кикни всех", "выкинь всех", "удали всех из войса",
    "отключи всех от войса", "вышвырни всех",
)

RUSSIAN_ROULETTE_ALIASES = (
    "русская рулетка", "русскую рулетку", "русской рулеткой",
    "рулетка", "рулетку",
)

RANDOM_TARGET_ALIASES = (
    "кого нибудь", "кого-нибудь", "кого нить", "кого то",
    "кого-то", "кого либо", "кому нибудь", "кому-нибудь",
    "кому то", "кому-то", "кому либо", "любого", "случайного",
    "случайному", "случайно", "какого нибудь", "какому нибудь",
    "рандомного", "рандомному", "рандомно", "наугад", "кого попало",
)

INSULT_WORDS = (
    # Обычные оскорбления.
    "дура", "дурочка", "дурень", "дурак", "тупая", "тупой", "тупица",
    "тупорылая", "тупорылый", "тупоголовая", "тупоголовый", "безмозглая",
    "безмозглый", "идиотка", "идиот", "дебилка", "дебил", "кретинка",
    "кретин", "имбецилка", "имбецил", "дегенератка", "дегенерат",
    "даун", "дауниха", "ничтожество", "убожество", "мерзость", "уродина",
    "урод", "чучело", "клоунесса", "клоун", "посмешище", "неудачница",
    "неудачник", "отброс", "мусор", "дно", "лохушка", "лошара", "лох",
    "чепушила", "чмоня", "чмо", "гнида", "крыса", "тварь", "падла",
    "сволочь", "сука", "шлюха", "шалава", "проститутка", "мразь",
    "животное", "обезьяна", "мартышка", "петух", "черт", "козел",
    "говно", "говнюк", "говноед", "говножуй", "говнохлеб", "говнохлебка",

    # Мат и составные/нишевые оскорбления.
    "уебок", "уебан", "уебище", "уебыш", "выблядок", "выродок",
    "долбоеб", "долбоящер", "еблан", "ебанат", "ебобо", "ебанько",
    "мудак", "мудила", "мудозвон", "гандон", "залупа", "залупоглаз",
    "хуила", "хуйло", "хуесос", "хуеплет", "хуеглот", "хуежуй",
    "хуемразь", "хуегрыз", "херосос", "пиздабол", "пиздун", "пиздюк",
    "пидор", "пидорас", "пидрила", "недоносок", "отморозок",
    "мамкоеб", "спермажуй", "сперможуй", "спермоед", "спермоглот",
    "спермосос", "спермобак", "котакбас", "котокбас", "кутакбас",
    "катакбас", "кодакбас",

    # Составные фразы тоже проверяются только после защищённого имени.
    "кусок говна", "ошибка природы", "позор семьи", "помойный отброс",
    "конченая мразь", "конченый мудак", "тупое животное", "ебаное чмо",
)

SEND_AWAY_PHRASES = (
    "иди нахуй", "пошла нахуй", "пошел нахуй", "пошёл нахуй",
    "пошли нахуй", "иди на хуй", "пошла на хуй", "пошел на хуй",
    "пошёл на хуй", "пошли на хуй", "на хуй", "иди нахер", "пошла нахер",
    "пошел нахер", "пошёл нахер", "иди нахрен", "пошла нахрен",
    "пошел нахрен", "пошёл нахрен", "иди в пизду", "пошла в пизду",
    "пошел в пизду", "пошёл в пизду", "пошли в пизду", "иди в жопу",
    "пошла в жопу", "пошел в жопу", "пошёл в жопу", "иди в очко",
    "отъебись", "от ебись", "съебись", "сьебись",
    # Одиночные «съеби» и «уйди» разрешены. Наказуем только усиленный
    # прямой посыл с матом после имени защищённой цели.
    "съеби нахуй", "сьеби нахуй", "с еби нахуй",
    "съеби на хуй", "сьеби на хуй", "с еби на хуй",
    "заебала", "заебал",
    "заткнись", "закрой рот", "закрой ебало", "завали рот",
    "завали ебало", "завали хлебало", "не пизди", "меньше пизди",
    "соси хуй", "сосать хуй", "иди соси", "хуй соси", "умри",
    "сдохни", "чтоб ты сдохла", "чтобы ты сдохла", "проваливай",
    "исчезни отсюда",
)

# Typical Russian Whisper substitutions for obscene words.  They are only
# used by the strict direct-target protection below; ambient profanity remains
# ordinary conversation and cannot trigger a moderation action by itself.
INSULT_SPEECH_REPLACEMENTS = (
    (r"\b(?:хуесос|хуисос|хуюсос|хуюс|хуесус|хуесыс|хорус|хорос|хорус)\b", "хуесос"),
    (r"\b(?:пидор|педор|пидар|педар|пидорас|педорас|пидорасик)\b", "пидор"),
    (r"\b(?:уебок|уебокк|уебан|уебанок|уебанчик|ебок)\b", "уебок"),
    (r"\b(?:долбоеб|долбаеб|далбоеб|долбоеба|долбаеба)\b", "долбоеб"),
    (r"\b(?:еблан|еблон|иблан|ебланчик)\b", "еблан"),
    (r"\b(?:мудак|мудаг|мудачок)\b", "мудак"),
    (r"\b(?:гандон|гандом|гондон)\b", "гандон"),
    (r"\b(?:соси|сасай|сосай|сосать)\s+(?:хуй|хуи|хую)\b", "соси хуй"),
    (r"\b(?:сперма\s*жуй|сперможуй|спермачуй|сперможуи|спермашуй|спермажуйка)\b", "спермажуй"),
    (r"\b(?:спермо\s*глот|спермаглот|спермоглод|спермоглотка)\b", "спермоглот"),
    (r"\b(?:спермо\s*ед|спермаед|спермоэт)\b", "спермоед"),
    (r"\b(?:котак\s*бас|коток\s*бас|кутак\s*бас|катак\s*бас|кодак\s*бас|котах\s*бас|кота\s+кбас)\b", "котакбас"),
    (r"\b(?:хуеплет|хуиплет|хуеплёт|хуяплет|хуе\s*плет)\b", "хуеплет"),
    (r"\b(?:хуеглот|хуиглот|хуе\s*глот)\b", "хуеглот"),
    (r"\b(?:хуежуй|хуижуй|хуе\s*жуй)\b", "хуежуй"),
    (r"\b(?:говножуй|говно\s*жуй|говнажуй)\b", "говножуй"),
    (r"\b(?:говноед|говнаед|говно\s*ед)\b", "говноед"),
    (r"\b(?:ебанат|ибанат|ебонат|ебанад)\b", "ебанат"),
    (r"\b(?:уебище|уебище|уебише|уибища)\b", "уебище"),
    (r"\b(?:чепушила|чипушила|чепушило|чепушилла)\b", "чепушила"),
    (r"\b(?:мудозвон|мудозвонн|мудазвон|мудозвонок)\b", "мудозвон"),
    (r"\b(?:дегенерат|дигенерат|дегенерад|дегенират)\b", "дегенерат"),
    (r"\b(?:иди|пошла|пошел|пошёл|пошли)\s+(?:на\s+)?(?:хуй|хуи|хую)\b", "иди нахуй"),
    (r"\b(?:иди|пошла|пошел|пошёл|пошли)\s+в\s+(?:пизду|пезду|пизду)\b", "иди в пизду"),
    (r"\b(?:от\s*ебись|отьебись|атъебись|отебись)\b", "отъебись"),
    (r"\b(?:с\s*ебись|сьебись|сьебись|съебись)\b", "съебись"),
    (r"\b(?:с\s*еби|сьеби|сьеби|съеби)\s+(?:на\s+)?(?:хуй|хуи|хую)\b", "съеби нахуй"),
)


ACTION_SPEECH_REPLACEMENTS = (
    # Recurring bounded GigaAM-v3 RNNT substitutions from the local command
    # corpus. A known target and a valid command are still required later.
    (r"\b(?:тикни|тихни|тикнет|сикни)\b", "кикни"),
    (r"\bтит\s+не\b", "кикни"),
    (r"\b(?:замутит|замус)\b", "замуть"),
    (r"\bзамок(?=\s+денис(?:а|у|ом)?\s+сердюк)", "замуть"),
    (r"\bна\s+(?:вроцк|вратск)([а-я]*)\b", r"навроцк\1"),
    # Искажения, подтвержденные реальным журналом Пятницы.
    (
        rf"\b(?:за\s*)?(?:мут|муд|мьют)(?={ATTACHED_TARGET_STEM_RE}\b)",
        "замуть ",
    ),
    (
        rf"\b(?:раз|рас)\s*(?:мут|муд|мьют|мой|мои|май)(?={ATTACHED_TARGET_STEM_RE}\b)",
        "размуть ",
    ),
    (
        rf"\b(?:кик|киг|ких|кип|кит)(?:ни|не|ну|ню)?(?={ATTACHED_TARGET_STEM_RE}\b)",
        "кикни ",
    ),
    (r"\b(?:каких|таких)\s+(?:не|ни)\b", "кикни"),
    (r"\b(?:какихни|такихни|какикни|такикни)\b", "кикни"),
    (r"\b(?:каких|таких|какик|такик)\s+(?:ни|не|ну|ню)\b", "кикни"),
    (r"\b(?:китни|кипни|кликни|кикмни|кикмне)\b", "кикни"),
    (r"\bкик\s+(?:мне|мни|ми)\b", "кикни"),
    (r"\b(?:за|са)\s+(?:мудь|муд|муть|мут|мой|мои|май)\b", "замуть"),
    (r"\b(?:раз|рас)\s+(?:мудь|муд|муть|мут|мьют)\b", "размуть"),
    (r"\b(?:размой|размои|размай|розмой|росмой|разумой|размойте|размоите)\b", "размуть"),
    (r"\b(?:замыть|замыл|замой|замои)\b", "замуть"),
    (r"\b(?:размыть|размыл|размой|размои)\b", "размуть"),
    (r"\bкикни\s+некогда\b", "кикни никиту"),
    (r"\bза\s+мудзиму\b", "замуть диму"),
    (r"\bза\s+муд\s+зиму\b", "замуть диму"),
    (r"\bза\s+(?:мой|мои|май)\s+(?=т?екит[а-я]*\b)", "замуть "),
    (r"\bза\s+(?:мой|мои|май)\s+(?=дим[а-я]*\b)", "замуть "),
    (r"\bза\s+(?:мой|мои|май)\s+(?=тазар[а-я]*\b)", "замуть "),
    (r"\bтекит(?:а|у|е)?\b", "никиту"),
    (r"\bтазар(?:а|у|е)?\b", "назара"),
    # Polite/plural imperatives and recurring Whisper consonant shifts.
    (r"\b(?:замутите|замутьте|замьютите|замьютьте|замудите|замудьте|замудьте)\b", "замуть"),
    (r"\b(?:размутите|размутьте|размьютите|размьютьте|размудите|размудьте|размудьте)\b", "размуть"),
    (r"\b(?:кикните|кикнете|кик\s+ните|кик\s+нете)\b", "кикни"),
    (r"\b(?:выкиньте|выкините|выкинете|вышвырните)\b", "выкинь"),
    (r"\b(?:выключите|вырубите)\b", "выключи"),
    (r"\b(?:отключите|отсоедините)\b", "отключи"),
    (r"\bвключите\b", "включи"),
    (r"\b(?:подключите|подсоедините)\b", "подключи"),
    (r"\b(?:верните|возвратите)\b", "верни"),
    (r"\b(?:заглушите|оглушите)\b", "заглуши"),
    (r"\bразглушите\b", "разглуши"),
    (r"\b(?:оффните|офните|оффаните|офаните)\b", "оффни"),
    (r"\bза\s+(?:мутите|мудите|мутьте|мудьте|мьютите)\b", "замуть"),
    (r"\bраз\s+(?:мутите|мудите|мутьте|мудьте|мьютите)\b", "размуть"),
    (r"\b(?:замудь|замуд|замуть|замути|замут|замють|замють)\b", "замуть"),
    (r"\b(?:размудь|размуд|размуть|размути|размут|размють|размють)\b", "размуть"),
    (r"\b(?:мудни|мудьни|мутни|мутьни|мьютни)\b", "замуть"),
    (r"\b(?:кигни|кихни|кижни|кижне|кекни|кейкни|кикне|кикну|кикню|кикны)\b", "кикни"),
    (r"\bкик\s+(?:ни|не|ну|ню|ны)\b", "кикни"),
    (r"\bза\s+(?:муть|мути|мут|мьют)\b", "замуть"),
    (r"\bраз\s+(?:муть|мути|мут|мьют)\b", "размуть"),
    (r"\b(?:за\s+(?:дэф|деф)|(?:дэф|деф)\s+ни)\b", "задеф"),
    (r"\bраз\s+глуш\b", "разглуш"),
    (r"\b(?:выключить|выключил|выключила|выключит|выключает|выключим|выключу|выключишь|выключаем|выруби|вырубил)\b", "выключи"),
    (r"\b(?:отключить|отключил|отключила|отключит|отключает|отсоедини)\b", "отключи"),
    (r"\b(?:включить|включил|включила|включит|включает|включим|включу|включишь|включаем)\b", "включи"),
    (r"\b(?:подключить|подключил|подключила|подключит|подсоедини)\b", "подключи"),
    (r"\b(?:вернуть|вернул|вернула|вернет|возврати)\b", "верни"),
    (r"\b(?:кикнуть|кикнул|кикнула|кикнет|кикает|кикнись)\b", "кикни"),
    (r"\b(?:выкинуть|выкинул|выкинет|выброси|выбросил)\b", "выкинь"),
    (r"\b(?:замьютить|замьютил|замутить|замутил|мьютни|мутни)\b", "замуть"),
    (r"\b(?:размьютить|размьютил|размутить|размутил)\b", "размуть"),
    (r"\b(?:заглушить|заглушил|заглушит)\b", "заглуши"),
    (r"\b(?:разглушить|разглушил|разглушит)\b", "разглуши"),
    (r"\b(?:микрофона|микрофону|микрофоном|микрафон|мекрофон|микрофончик)\b", "микрофон"),
    (r"\b(?:звука|звуку|звуком|зук|звукк)\b", "звук"),
    (r"\b(?:микрафан|мекрафон|микрофонн|микрофончик)\b", "микрофон"),
    (r"\b(?:зфук|свук|звучок)\b", "звук"),
    (r"\b(?:войса|войсе|войс|голосового|голосовом)\b", "войс"),
)


def normalize_discord_speech(text):
    text = str(text or "").lower()

    text = text.replace("ё", "е")

    text = re.sub(
        r"[^a-zа-я0-9\s-]",
        " ",
        text
    )

    text = " ".join(
        text.split()
    )

    for pattern, replacement in ACTION_SPEECH_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)

    for pattern, replacement in INSULT_SPEECH_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)

    return " ".join(text.split())


def _norm(text):
    return normalize_discord_speech(text)


def _contains_phrase(text, phrase):
    text = _norm(text)
    phrase = _norm(phrase)

    return bool(
        re.search(
            rf"(?<![a-zа-я0-9])"
            rf"{re.escape(phrase)}"
            rf"(?![a-zа-я0-9])",
            text,
        )
    )


def _contains_any(text, phrases):
    return any(
        _contains_phrase(text, phrase)
        for phrase in phrases
    )


def is_protected_insult(text):
    """Match only an unambiguous direct insult aimed at a protected target.

    Speech recognition can append fragments from other people.  In particular,
    the former ``insult + name`` form treated an ordinary rant as an attack
    when a protected name happened to appear later in the transcript.
    """
    t = _norm(text)
    targets = tuple(dict.fromkeys(
        ALIASES["mashonka"]
        + ALIASES["danya_vip"]
        + tuple(wake_aliases("friday", ("пятница", "пятничка", "пятницу", "пятнице")))
    ))
    target_pattern = "(?:" + "|".join(
        re.escape(_norm(alias)) for alias in sorted(targets, key=len, reverse=True)
    ) + ")"
    insult_pattern = "(?:" + "|".join(
        re.escape(_norm(alias)) for alias in sorted(INSULT_WORDS, key=len, reverse=True)
    ) + ")"
    send_pattern = "(?:" + "|".join(
        re.escape(_norm(alias)) for alias in sorted(SEND_AWAY_PHRASES, key=len, reverse=True)
    ) + ")"
    modifier = r"(?:\s+(?:ты|вы|такая|такой|просто|реально|очень|ебаная|ебаный)){0,2}"
    # The protected name must come first.  This accepts clear phrases such as
    # «Даня, ты ...», «Пятница тупая», «Пятница иди ...», while rejecting
    # ambient profanity and the ambiguous «... [insult] ... Даня» pattern.
    return bool(
        re.search(rf"\b{target_pattern}\b{modifier}\s+{insult_pattern}\b", t)
        # Double braces are required inside an f-string.  The former {0,2}
        # became the literal tuple ``(0, 2)`` and broke every send-away match.
        or re.search(rf"\b{target_pattern}\b(?:\s+(?:ты|вы|же|сам|сама|ну|давай|просто|вообще)){{0,3}}\s+{send_pattern}\b", t)
    )


def _bounded_edit_distance(left, right, limit):
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for row, char_left in enumerate(left, 1):
        current = [row]
        row_min = row
        for column, char_right in enumerate(right, 1):
            value = min(
                current[column - 1] + 1,
                previous[column] + 1,
                previous[column - 1] + (char_left != char_right),
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _fuzzy_word_score(word, alias):
    word = _norm(word)
    alias = _norm(alias)
    if " " in alias or len(word) < 4 or len(alias) < 4:
        return None
    limit = 2 if max(len(word), len(alias)) >= 8 else 1
    distance = _bounded_edit_distance(word, alias, limit)
    return distance if distance <= limit else None


def _contains_action(text, aliases):
    if _contains_any(text, aliases):
        return True
    tokens = re.findall(r"[a-zа-я]+", _norm(text), flags=re.IGNORECASE)
    return any(
        _fuzzy_word_score(token, alias) is not None
        for token in tokens
        for alias in aliases
    )


# ------------------------------------------------------------
# PEOPLE
# ------------------------------------------------------------

def resolve_people(text):
    t = _norm(text)

    found = []

    candidates = []

    for key, aliases in ALIASES.items():
        for alias in aliases:
            candidates.append(
                (
                    len(_norm(alias)),
                    key,
                    alias,
                )
            )

    # Самые специфичные имена ищем первыми.
    candidates.sort(
        reverse=True
    )

    for _, key, alias in candidates:
        if _contains_phrase(
            t,
            alias
        ):
            if key not in found:
                found.append(key)

    # If there was no exact name, accept only one unambiguous closest person.
    # Ties are rejected: guessing the wrong Discord member is worse than asking
    # the speaker to repeat the command.
    if not found:
        best_by_key = {}
        tokens = re.findall(r"[a-zа-я]+", t, flags=re.IGNORECASE)
        for key, aliases in ALIASES.items():
            scores = [
                score
                for token in tokens
                for alias in aliases
                if (score := _fuzzy_word_score(token, alias)) is not None
            ]
            if scores:
                best_by_key[key] = min(scores)
        if best_by_key:
            best_score = min(best_by_key.values())
            winners = [
                key
                for key, score in best_by_key.items()
                if score == best_score
            ]
            winner_set = frozenset(winners)
            grouped_tie = any(
                winner_set == group
                for group in ACCOUNT_GROUPS
            )
            if len(winners) == 1 or grouped_tie:
                found.append(winners[0])
                found.extend(winners[1:])

    # Если конкретный Денис уже найден,
    # второго автоматически не добавляем.
    # A surname/nickname overrides the shared «Никита» alias. This keeps
    # «Никита Польский» person-specific while plain «Никита» targets all.
    nikita_keys = set(NIKITA_SPECIFIC_ALIASES)
    specific_nikitas = []
    tokens = re.findall(r"[a-zа-я]+", t, flags=re.IGNORECASE)
    for key, aliases in NIKITA_SPECIFIC_ALIASES.items():
        if _contains_any(t, aliases) or any(
            _fuzzy_word_score(token, alias) is not None
            for token in tokens
            for alias in aliases
        ):
            specific_nikitas.append(key)
    if specific_nikitas:
        found = [key for key in found if key not in nikita_keys]
        found.extend(specific_nikitas)

    denis_specific = (
        "barashka" in found
        or
        "denisserguck" in found
    )

    if not denis_specific:
        if _contains_any(
            t,
            DENIS_SHARED
        ):
            found.extend(
                (
                    "barashka",
                    "denisserguck",
                )
            )

    return list(
        dict.fromkeys(found)
    )


# ------------------------------------------------------------
# PARSER
# ------------------------------------------------------------

def parse_discord_voice_command(text):
    t = _norm(text)

    action = None

    if SELF_DISCONNECT_RE.fullmatch(t):
        return {
            "action": "self_disconnect",
            "targets": [],
        }

    if _contains_any(t, GENOCIDE_ALIASES):
        return {
            "action": "genocide",
            "targets": [],
        }

    if t in RUSSIAN_ROULETTE_ALIASES:
        return {
            "action": "random_disconnect",
            "targets": [],
        }

    # --------------------------------------------------------
    # FULL OFF TOGGLE
    #
    # Проверяем ПЕРВЫМ, потому что:
    # "отключи полностью ..."
    # не должно превратиться в другое действие.
    # --------------------------------------------------------

    if _contains_action(
        t,
        FULL_RESTORE_ALIASES
    ):
        action = "full_restore"

    elif _contains_action(
        t,
        FULL_DISABLE_ALIASES
    ):
        action = "full_disable"

    elif _contains_action(
        t,
        OFF_ALIASES
    ):
        action = "off_toggle"

    # --------------------------------------------------------
    # UNMUTE
    # --------------------------------------------------------

    elif _contains_action(
        t,
        UNMUTE_ALIASES
    ):
        action = "unmute"

    # --------------------------------------------------------
    # MUTE
    # --------------------------------------------------------

    elif _contains_action(
        t,
        MUTE_ALIASES
    ):
        action = "mute"

    # --------------------------------------------------------
    # UNDEAF
    # --------------------------------------------------------

    elif _contains_action(
        t,
        UNDEAF_ALIASES
    ):
        action = "undeaf"

    # --------------------------------------------------------
    # DEAF
    # --------------------------------------------------------

    elif _contains_action(
        t,
        DEAF_ALIASES
    ):
        action = "deaf"

    # --------------------------------------------------------
    # DISCONNECT
    # --------------------------------------------------------

    elif _contains_action(
        t,
        DISCONNECT_ALIASES
    ):
        action = "disconnect"

    # --------------------------------------------------------
    # Реальные искажения Vosk для kick:
    #
    # "кикни Никиту из войса"
    # ->
    # "к ней никиту из войск"
    # --------------------------------------------------------

    elif (
        _contains_any(
            t,
            (
                "к ней",
                "к не",
            )
        )
        and
        _contains_any(
            t,
            (
                "из войса",
                "из войск",
                "из пояса",
            )
        )
    ):
        action = "disconnect"

    if action is None:
        return None

    # Spoken self-correction inside one utterance:
    # «кикни Никиту, ой нет, Диму» keeps the action but replaces the target.
    # Only switch to the tail when it contains a known person, so ordinary
    # phrases with «нет» cannot accidentally erase a valid target.
    target_scope = t
    correction_patterns = (
        r"\bой\s+нет\b",
        r"\bа\s+нет\b",
        r"\bнет\s+лучше\b",
        r"\b(?:точнее|вернее)\b",
        r"\bя\s+имел(?:а)?\s+в\s+виду\b",
        r"\bне\b[^.?!]{1,80}?\bа\b",
    )
    latest_correction = None
    for pattern in correction_patterns:
        matches = list(re.finditer(pattern, t, flags=re.IGNORECASE))
        if matches and (latest_correction is None or matches[-1].end() > latest_correction.end()):
            latest_correction = matches[-1]
    if latest_correction is not None:
        corrected_tail = t[latest_correction.end():].strip()
        if corrected_tail and resolve_people(corrected_tail):
            target_scope = corrected_tail

    targets = resolve_people(target_scope)

    if not targets and _contains_any(t, RANDOM_TARGET_ALIASES):
        action = f"random_{action}"

    return {
        "action": action,
        "targets": targets,
    }


# ------------------------------------------------------------
# HTTP BRIDGE
# ------------------------------------------------------------

def _request(
    path,
    method="GET",
    payload=None,
    timeout=3.0,
):
    url = (
        BRIDGE_URL
        + path
    )

    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(
            payload
        ).encode(
            "utf-8"
        )

        headers[
            "Content-Type"
        ] = (
            "application/json; charset=utf-8"
        )

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=timeout,
        ) as response:

            raw = (
                response
                .read()
                .decode("utf-8")
            )

            return json.loads(raw)

    except urllib.error.HTTPError as exc:
        try:
            raw = (
                exc
                .read()
                .decode("utf-8")
            )

            return json.loads(raw)

        except Exception:
            return {
                "ok": False,
                "error": (
                    f"HTTP {exc.code}"
                ),
            }

    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def bridge_health():
    return _request(
        "/health"
    )


def voice_members():
    return _request(
        "/voice-members"
    )


def voice_action(
    action,
    targets,
    actor_user_id=None,
):
    return _request(
        "/voice/action",
        method="POST",
        payload={
            "action": action,
            "targets": list(targets),
            "actorUserId": str(actor_user_id or ""),
        },
    )


# ------------------------------------------------------------
# RESPONSE HELPERS
# ------------------------------------------------------------

def _human_targets(targets, grammatical_case="nominative"):
    names = DISPLAY_NAMES_BY_CASE.get(
        grammatical_case,
        DISPLAY_NAMES_BY_CASE["nominative"],
    )
    labels = [
        names.get(key, key)
        for key in targets
    ]
    return ", ".join(dict.fromkeys(labels))


def group_voice_action(mode, action, actor_user_id=None):
    return _request(
        "/voice/group-action",
        method="POST",
        payload={
            "mode": mode,
            "action": action,
            "actorUserId": str(actor_user_id or ""),
        },
        timeout=8.0,
    )


def _group_action_result(response, action, mode):
    if not response.get("ok"):
        if response.get("error") == "group_action_forbidden":
            return "У тебя нет права на эту групповую команду."
        if response.get("error") in {"discord_not_ready", "bridge_unavailable"}:
            return "Связь с Discord сейчас не готова."
        if not response.get("results"):
            return "В голосовом канале сейчас некого выбирать."
        return "Не удалось выполнить групповую команду."
    done = [item for item in response.get("results", []) if item.get("ok")]
    names = ", ".join(
        dict.fromkeys(str(item.get("displayName") or item.get("username") or item.get("key")) for item in done)
    )
    if mode == "all":
        return f"Геноцид выполнен. Кикнул: {names}."
    action_text = {
        "disconnect": "Случайно кикнул",
        "mute": "Случайно отключил микрофон",
        "deaf": "Случайно отключил звук",
    }[action]
    return f"{action_text}: {names}."


def _successful_keys(response):
    return [
        item.get("key")
        for item in response.get(
            "results",
            []
        )
        if (
            item.get("ok")
            and
            item.get("key")
        )
    ]


def _failed_results(response):
    return [
        item
        for item in response.get(
            "results",
            []
        )
        if not item.get("ok")
    ]


def _bridge_error(response):
    if response.get("results"):
        return None

    return response.get(
        "error",
        "DiscordBot не ответил"
    )


# ------------------------------------------------------------
# NORMAL ACTION
# ------------------------------------------------------------

def _execute_normal_action(
    action,
    targets,
    actor_user_id=None,
):
    response = voice_action(
        action,
        targets,
        actor_user_id=actor_user_id,
    )

    error = _bridge_error(
        response
    )

    if error:
        return (
            "Не удалось выполнить команду Discord: "
            f"{error}"
        )

    done = _successful_keys(
        response
    )

    failed = _failed_results(
        response
    )

    # For one person with several Discord accounts, absence of a secondary
    # account is normal.  If at least one account succeeded, do not pollute the
    # spoken/log result with “not in voice/server” for its siblings.
    done_set = set(done)
    successful_groups = [
        group
        for group in ACCOUNT_GROUPS
        if done_set & group
    ]
    if successful_groups:
        failed = [
            item
            for item in failed
            if not any(
                item.get("key") in group
                and item.get("status") in {"not_in_voice", "not_on_server"}
                for group in successful_groups
            )
        ]

    action_text = {
        "disconnect":
            "Кикнул",

        "mute":
            "Отключил микрофон",

        "unmute":
            "Включил микрофон",

        "deaf":
            "Отключил звук",

        "undeaf":
            "Включил звук",
    }.get(
        action,
        "Готово для"
    )

    parts = []

    if done:
        result_case = (
            "accusative"
            if action == "disconnect"
            else "dative"
        )
        parts.append(
            f"{action_text} "
            f"{_human_targets(done, result_case)}."
        )

    not_voice = [
        item.get("key")
        for item in failed
        if (
            item.get("status")
            == "not_in_voice"
        )
    ]

    protected = [
        item.get("key")
        for item in failed
        if (
            item.get("status")
            == "protected"
        )
    ]

    not_server = [
        item.get("key")
        for item in failed
        if (
            item.get("status")
            == "not_on_server"
        )
    ]

    other = [
        item.get("key")
        for item in failed
        if (
            item.get("status")
            not in {
                "not_in_voice",
                "protected",
                "not_on_server",
            }
        )
    ]

    if not_voice:
        parts.append(
            "Сейчас не в войсе: "
            f"{_human_targets(not_voice, 'nominative')}."
        )

    if protected:
        parts.append(
            "Защищённого пользователя "
            "не трогаю."
        )

    if not_server:
        parts.append(
            "Сейчас не на сервере: "
            f"{_human_targets(not_server, 'nominative')}."
        )

    if other:
        parts.append(
            "Discord вернул ошибку для: "
            f"{_human_targets(other, 'nominative')}."
        )

    if parts:
        return " ".join(parts)

    return "Команда Discord не выполнена."


# ------------------------------------------------------------
# FULL OFF TOGGLE
# ------------------------------------------------------------

def _execute_off_toggle(
    targets
):
    """
    Одна команда переключает два server-state:

        OFF:
            mute = true
            deaf = true

        ON:
            mute = false
            deaf = false

    Пока состояние хранится локально в Python.
    """

    to_disable = []
    to_restore = []

    for key in targets:
        if OFF_STATE.get(
            key,
            False
        ):
            to_restore.append(key)
        else:
            to_disable.append(key)

    final_parts = []

    # --------------------------------------------------------
    # FULL OFF
    # --------------------------------------------------------

    if to_disable:
        mute_response = voice_action(
            "mute",
            to_disable
        )

        mute_error = _bridge_error(
            mute_response
        )

        if mute_error:
            return (
                "Не удалось выполнить полный мут: "
                f"{mute_error}"
            )

        mute_ok = set(
            _successful_keys(
                mute_response
            )
        )

        # Deaf отправляем только тем,
        # кому mute реально прошёл.
        if mute_ok:
            deaf_response = voice_action(
                "deaf",
                list(mute_ok)
            )

            deaf_error = _bridge_error(
                deaf_response
            )

            if deaf_error:
                # Mute уже мог примениться.
                return (
                    "Микрофон отключился, "
                    "но звук отключить не удалось: "
                    f"{deaf_error}"
                )

            deaf_ok = set(
                _successful_keys(
                    deaf_response
                )
            )

            fully_off = (
                mute_ok
                &
                deaf_ok
            )

            for key in fully_off:
                OFF_STATE[key] = True

            if fully_off:
                final_parts.append(
                    "Выключил микрофон и звук "
                    f"{_human_targets(fully_off, 'dative')}."
                )

        failed = _failed_results(
            mute_response
        )

        not_voice = [
            item.get("key")
            for item in failed
            if (
                item.get("status")
                == "not_in_voice"
            )
        ]

        if not_voice:
            final_parts.append(
                "Сейчас не в войсе: "
                f"{_human_targets(not_voice, 'nominative')}."
            )

    # --------------------------------------------------------
    # RESTORE
    # --------------------------------------------------------

    if to_restore:
        unmute_response = voice_action(
            "unmute",
            to_restore
        )

        unmute_error = _bridge_error(
            unmute_response
        )

        if unmute_error:
            return (
                "Не удалось вернуть звук: "
                f"{unmute_error}"
            )

        unmute_ok = set(
            _successful_keys(
                unmute_response
            )
        )

        if unmute_ok:
            undeaf_response = voice_action(
                "undeaf",
                list(unmute_ok)
            )

            undeaf_error = _bridge_error(
                undeaf_response
            )

            if undeaf_error:
                return (
                    "Микрофон включился, "
                    "но звук вернуть не удалось: "
                    f"{undeaf_error}"
                )

            undeaf_ok = set(
                _successful_keys(
                    undeaf_response
                )
            )

            restored = (
                unmute_ok
                &
                undeaf_ok
            )

            for key in restored:
                OFF_STATE[key] = False

            if restored:
                final_parts.append(
                    "Включил микрофон и звук "
                    f"{_human_targets(restored, 'dative')}."
                )

        failed = _failed_results(
            unmute_response
        )

        not_voice = [
            item.get("key")
            for item in failed
            if (
                item.get("status")
                == "not_in_voice"
            )
        ]

        if not_voice:
            # Если человек вышел из войса,
            # сбрасываем локальный toggle.
            for key in not_voice:
                OFF_STATE[key] = False

            final_parts.append(
                "Сейчас не в войсе: "
                f"{_human_targets(not_voice, 'nominative')}."
            )

    if final_parts:
        return " ".join(
            final_parts
        )

    return (
        "Полный мут не удалось выполнить."
    )


def _execute_full_restore(targets):
    """Force server unmute + undeaf without relying on toggle history."""
    for key in targets:
        OFF_STATE[key] = True
    return _execute_off_toggle(targets)


def _execute_full_disable(targets):
    """Force server mute + deafen without relying on toggle history."""
    for key in targets:
        OFF_STATE[key] = False
    return _execute_off_toggle(targets)


def _speaker_key(user_id):
    """Resolve the exact Discord account that produced the voice command."""
    wanted = str(user_id or "").strip()
    if not wanted:
        return None

    payload = voice_members()
    if not payload.get("ok"):
        return None

    for member in payload.get("members", []):
        if str(member.get("id", "")) == wanted:
            key = member.get("key")
            return str(key) if key else None

    return None


def execute_protected_insult(text, actor_user_id=None):
    if not actor_user_id or not is_protected_insult(text):
        return None
    speaker = _speaker_key(actor_user_id)
    if not speaker:
        return "Оскорбление ВИП замечено, но говорящий не найден."
    if speaker in VIP_IMMUNE_SPEAKER_KEYS:
        return "Skeeladoom — ВИП. Его не трогаю."
    return _execute_normal_action("disconnect", [speaker])


# ------------------------------------------------------------
# PUBLIC EXECUTOR
# ------------------------------------------------------------

def execute_discord_voice_command(
    text,
    actor_user_id=None,
):
    parsed = (
        parse_discord_voice_command(
            text
        )
    )

    if parsed is None:
        return None

    return execute_discord_parsed_command(parsed, actor_user_id=actor_user_id)


def execute_discord_parsed_command(parsed, actor_user_id=None):
    """Выполнить уже разобранную команду без повторного нечёткого разбора."""
    if not isinstance(parsed, dict):
        return None

    action = parsed[
        "action"
    ]

    targets = parsed[
        "targets"
    ]

    if action == "self_disconnect":
        speaker = _speaker_key(actor_user_id)
        if not speaker:
            return (
                "Не удалось определить, кто произнёс команду, "
                "или говорящего уже нет в голосовом канале."
            )
        # Это единственное добровольное исключение из VIP-иммунитета:
        # команда действует только на самого говорящего.
        return _execute_normal_action(
            "disconnect",
            [speaker],
            actor_user_id=actor_user_id,
        )

    if action == "genocide":
        return _group_action_result(
            group_voice_action("all", "disconnect", actor_user_id=actor_user_id),
            "disconnect",
            "all",
        )

    if action.startswith("random_"):
        random_action = action.removeprefix("random_")
        if random_action not in {"disconnect", "mute", "deaf"}:
            return "Для случайного выбора эта команда недоступна."
        return _group_action_result(
            group_voice_action("random", random_action, actor_user_id=actor_user_id),
            random_action,
            "random",
        )

    if not targets:
        return (
            "Не понял, кого именно "
            "ты имеешь в виду."
        )

    attacked_protected = [
        key for key in targets
        if key in RETALIATION_PROTECTED_KEYS
    ]
    retaliation = bool(
        attacked_protected
        and action in RETALIATION_ACTIONS
        and actor_user_id
    )

    if retaliation:
        speaker = _speaker_key(actor_user_id)
        if not speaker:
            return (
                "Попытка тронуть ВИП заблокирована. "
                "Не удалось определить, кто отдал команду."
            )
        # Skeeladoom is a full VIP.  Retaliation must never bounce an action
        # back onto him, including when he names himself as the target.
        if speaker in VIP_IMMUNE_SPEAKER_KEYS:
            return (
                "Skeeladoom — ВИП. "
                "Его кикать или заглушать нельзя."
            )
        targets = [speaker]

    protected_targets = [
        key for key in targets
        if key in PROTECTED_LOCAL_KEYS
    ]
    targets = [
        key for key in targets
        if key not in PROTECTED_LOCAL_KEYS
    ]

    protected_text = ""
    if protected_targets:
        protected_text = (
            "Даня — ВИП. Его трогать нельзя."
        )

    if not targets:
        return protected_text

    if action == "off_toggle":
        if retaliation:
            for key in targets:
                OFF_STATE[key] = False
        result = _execute_off_toggle(
            targets
        )
    elif action == "full_disable":
        result = _execute_full_disable(
            targets
        )
    elif action == "full_restore":
        result = _execute_full_restore(
           targets
        )
    else:
        result = _execute_normal_action(
            action,
            targets,
            actor_user_id=actor_user_id,
        )

    return " ".join(
        part for part in (result, protected_text)
        if part
    )
