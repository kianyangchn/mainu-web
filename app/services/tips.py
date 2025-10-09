"""Travel and cuisine tip service using curated Wikivoyage cuisine links."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class Tip:
    """Structured payload describing a single loading-state insight."""

    title: str
    body: str
    image_url: str | None = None
    source_name: str | None = None
    source_url: str | None = None


_MAX_BODY_LENGTH = 100


@dataclass(frozen=True)
class _CuisineInfo:
    slug: str
    title: str
    description: str
    image: str


def _trim(text: str) -> str:
    if len(text) <= _MAX_BODY_LENGTH:
        return text
    return text[: _MAX_BODY_LENGTH - 1].rstrip() + "…"


_CURATED_CUISINES: tuple[_CuisineInfo, ...] = (
    _CuisineInfo(
        slug="Street_food",
        title="Street food",
        description=(
            "Colourful and diverse, street food is an experience you can find in cities and "
            "towns all around the world. It's generally convenient and cheap, but its appeal "
            "goes far beyond that. Street food can be simple yet utterly delicious, and it's "
            "often a great way to sample some authentic local cuisine. Joining locals around "
            "bustling little street stalls can open doors and lead to memorable encounters. "
            "In some countries, whether you're a typical foodie or not, you may find that "
            "your search for great street food turns out to be among the best experiences of "
            "your trip."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/b/bf/Forodhani_park_food_stand.jpg",
    ),
    _CuisineInfo(
        slug="Overseas_Chinese_cuisine",
        title="Overseas Chinese cuisine",
        description=(
            "While Chinese cuisine may have originated in China, the legacy of the Overseas "
            "Chinese has brought the flavours, ingredients and cuisine of China all around "
            "the world. By far the most well known types of \"Overseas Chinese\" cuisines "
            "can be found in the sizable Chinese minorities in Southeast Asia, but there are "
            "also local styles in places like Australia and the Americas."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/5/51/%E6%B0%B4%E7%85%AE%E9%B1%BC_Spicy_Fish_with_Rice_-_Spicy_Fish%2C_Glen_Waverley_%283012467062%29.jpg",
    ),
    _CuisineInfo(
        slug="Western_food_in_Asia",
        title="Western food in Asia",
        description=(
            "Western food in Asia is often localised to the point of being hardly "
            "recognisable to Westerners, a situation analogous to Asian, in particular "
            "Chinese, cuisines in the West. This article aims to provide an overview of the "
            "unique variations on Western food that have developed in Asia that visitors "
            "might be interested in trying."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/4/4c/Zhazhupai_in_Shanghai02.jpg",
    ),
    _CuisineInfo(
        slug="Australian_cuisine",
        title="Australian cuisine",
        description=(
            "Australian cuisine is hard to pin down: in this nation of immigrants, "
            "restaurants claiming to offer it are few and far between, and the word tends to "
            "either evoke meat-and-three-veg British stodge or tourist-trap restaurants "
            "hawking kangaroo burgers and crocodile kebabs. Yet with amazing local produce, "
            "influences from cuisines from all over the world, and an exciting Modern "
            "Australian food scene awaiting those not afraid to experiment, there are plenty "
            "of incredible eats and drinks to be found."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/1/12/Chicken_parmigiana.jpg",
    ),
    _CuisineInfo(
        slug="Burmese_cuisine",
        title="Burmese cuisine",
        description=(
            "Burmese cuisine reflects the history, ethnic and climatic diversity of Myanmar. "
            "Less well known than the neighbouring cuisines of China, India and Thailand due "
            "to a smaller diaspora and reclusive government in modern times, the cuisine of "
            "Myanmar shares many features with its neighbours but is full of unique dishes "
            "and flavours as well."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/6/64/Laphet_thoke.JPG",
    ),
    _CuisineInfo(
        slug="Cambodian_cuisine",
        title="Cambodian cuisine",
        description=(
            "Cambodian cuisine is one of the most underrated and overlooked cuisines in "
            "Asia. It encompasses the food cultures of all Cambodia's ethnic groups – the "
            "Khmers, Khmer Loeu, Vietnamese, Chams, Mountain Chams, Lao and the Chinese. At "
            "the core of Cambodian cuisine lies Khmer cuisine (សិល្បៈធ្វើម្ហូបខ្មែរ), the "
            "nearly-two-thousand-year-old culinary art of the Khmer people native to "
            "modern-day Cambodia and other parts of the former Khmer Empire. Over centuries, "
            "Cambodian cuisine has incorporated elements of Indian, Chinese, Portuguese, and "
            "more recently French cuisine, and due to some of these shared influences and "
            "mutual interaction, it has many similarities with the cuisines of Central "
            "Thailand, and Southern Vietnam and to a lesser extent also Central Vietnam, "
            "Northeastern Thailand and Laos."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/2/2d/Bas-relief_du_Bayon_%28Angkor_Thom%29_%282341905162%29.jpg",
    ),
    _CuisineInfo(
        slug="Central_Asian_cuisine",
        title="Central Asian cuisine",
        description=(
            "The cuisine of Central Asia reflects its history and cultural influences with "
            "its Turko-Mongol nomadic heritage, Silk Road connections, Persian and Russian "
            "rule and Islamic dietary laws all shaping the food eaten in the region. You "
            "will find common dishes throughout Central Asia as well as dishes unique to one "
            "or two countries."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/d/db/%D0%91%D0%B5%D1%88%D0%B1%D0%B0%D1%80%D0%BC%D0%B0%D0%BA_%D0%B8%D0%B7_%D0%B3%D0%BE%D0%B2%D1%8F%D0%B4%D0%B8%D0%BD%D1%8B_03.jpg",
    ),
    _CuisineInfo(
        slug="Chinese_cuisine",
        title="Chinese cuisine",
        description=(
            "The origins of Chinese cuisine can be traced back millennia. Chinese cuisine is "
            "extremely diverse with wide regional variations, and it is not uncommon for "
            "even Chinese people to disagree on which ingredients should be in certain "
            "dishes or how they should be cooked."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/1/17/Chiuchow_cuisine.jpg",
    ),
    _CuisineInfo(
        slug="Filipino_cuisine",
        title="Filipino cuisine",
        description=(
            "Filipino cuisine is a reflection of several cultures of the Philippines and is "
            "a medley of different dishes that incorporate the traditions of the indigenous "
            "peoples as well as those of the neighbouring countries such as Malaysia and "
            "China, colonizers such as Spain and the United States, and even those who came "
            "to Philippines for business such as India and Japan."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/0/0a/Philippine_cuisine_%2827901955835%29.jpg",
    ),
    _CuisineInfo(
        slug="Indonesian_cuisine",
        title="Indonesian cuisine",
        description=(
            "Indonesian cuisine is an umbrella term referring to the culinary traditions "
            "spanning the archipelago of Indonesia, using different ingredients and spices "
            "to create a rich and flavourful masterpiece. It has left strong influences on "
            "the cuisine of neighbouring Malaysia and Singapore and can also be found in "
            "other countries that have long associations with Indonesia, such as the "
            "Netherlands and Suriname."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/0/07/Nasi_Goreng_in_Bali.jpg",
    ),
    _CuisineInfo(
        slug="Japanese_cuisine",
        title="Japanese cuisine",
        description=(
            "The cuisine of Japan is well known for its sushi (vinegar-seasoned rice and raw "
            "fish) and sashimi (sliced raw fish), which are well liked around the world. "
            "However, there are many more Japanese foods that are savoury to the tongue; a "
            "few of these are ramen noodles, yakitori chicken, and tempura shrimp."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/7/76/Sushi_platter.jpg",
    ),
    _CuisineInfo(
        slug="Korean_cuisine",
        title="Korean cuisine",
        description=(
            "The cuisine of Korea is based primarily on rice, vegetables and meats, and was "
            "historically influenced by the country's turbulent history and strong religious "
            "beliefs. Korean cuisine is also influenced by Japan and China and vice versa."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/0/0b/Korean.table.setting.kimchi.jpg",
    ),
    _CuisineInfo(
        slug="Cuisine_of_Malaysia,_Singapore_and_Brunei",
        title="Cuisine of Malaysia, Singapore and Brunei",
        description=(
            "Malaysia, Singapore and Brunei share similar food, owing to their common "
            "history and culture. Many dishes have elements from Malay, Chinese, Indian, and "
            "Occidental cuisines, as well as elements from other cuisines."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/7/7d/Teh_Tarik_Malaysia.jpg",
    ),
    _CuisineInfo(
        slug="Middle_Eastern_cuisine",
        title="Middle Eastern cuisine",
        description=(
            "Middle Eastern cuisine can be used as a blanket term to describe the cuisines "
            "of the people living in the Middle East. The most prominent among these "
            "cuisines is Levantine cuisine, which includes the cooking traditions of the "
            "eastern Mediterranean."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/b/bc/Mezze%2C_spread.jpg",
    ),
    _CuisineInfo(
        slug="South_Asian_cuisine",
        title="South Asian cuisine",
        description=(
            "South Asia is a region with great geological, climatic, cultural and religious "
            "diversity, so it is no surprise that the culinary traditions vary greatly as "
            "well."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/3/32/South_Indian_Tali.jpg",
    ),
    _CuisineInfo(
        slug="Thai_cuisine",
        title="Thai cuisine",
        description=(
            "Thai cuisine is a fusion of centuries-old influences and today's innovations. "
            "Thai food is best known for being spicy, but most dishes employ a balance of "
            "ingredients to achieve the five fundamental tastes: spicy, sour, sweet, salty, "
            "and bitter, in each dish or across the Thai meal."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/7/7b/Pad_Thai_kung_Chang_Khien_street_stall.jpg",
    ),
    _CuisineInfo(
        slug="Vietnamese_cuisine",
        title="Vietnamese cuisine",
        description=(
            "Vietnamese cuisine is known for light, fresh flavours that balance sweet, sour, "
            "salty and spicy. Dishes are often loaded with fresh herbs, fish sauce, and rice "
            "noodles or jasmine rice."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/2/26/Ph%E1%BB%9F_B%C3%B2.jpg",
    ),
    _CuisineInfo(
        slug="North_African_cuisine",
        title="North African cuisine",
        description=(
            "North African cuisine reflects the region's diverse history and climate. It has "
            "common elements including couscous, tagines and spices, but each country also "
            "has its own specialities."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/a/a1/Couscous_bianco_e_verdure_arrostite.jpg",
    ),
    _CuisineInfo(
        slug="Nigerian_cuisine",
        title="Nigerian cuisine",
        description=(
            "Nigerian cuisine derives from the country's diversified ethnic groups, which "
            "range from the northern (Hausa, Fulani) to the southern (Yoruba and Igbo)."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/4/42/Ofada-rice.jpg",
    ),
    _CuisineInfo(
        slug="American_cuisine",
        title="American cuisine",
        description=(
            "American cuisine isn't easy to define. Regional cuisines from Texas to Maine to "
            "Hawaii borrow from 200+ years of immigration to produce hybrid dishes and "
            "Americanized versions of dishes from Europe, Africa, and Asia."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/0/02/American_cuisine.jpg",
    ),
    _CuisineInfo(
        slug="Chain_restaurants_in_the_United_States_and_Canada",
        title="Chain restaurants in the United States and Canada",
        description=(
            "In the United States and Canada, there are countless chain restaurants that are "
            "almost ubiquitous across North America, as well as some that are specific to a "
            "particular region."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/5/58/Olive_Garden_logo_on_building.jpg",
    ),
    _CuisineInfo(
        slug="Fast_food_in_the_United_States_and_Canada",
        title="Fast food in the United States and Canada",
        description=(
            "Fast food is a broad term for inexpensive food served quickly at venues ranging "
            "from drive-through restaurants to hot dog carts on a street corner."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/7/7a/McDonald%27s_Supersized_meal.jpg",
    ),
    _CuisineInfo(
        slug="Pizza_in_the_United_States_and_Canada",
        title="Pizza in the United States and Canada",
        description=(
            "Pizza is one of the foods one is most likely to encounter on a visit to the "
            "United States."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/7/7f/NY_style_pizza_slice.jpg",
    ),
    _CuisineInfo(
        slug="Argentine_cuisine",
        title="Argentine cuisine",
        description=(
            "Argentine cuisine is known among meat-lovers for steak and barbecues, but there "
            "is much more to explore – especially dishes with Italian, Spanish and indigenous "
            "roots, desserts and sweets, and a passion for wine."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/1/1d/Asado_2.jpg",
    ),
    _CuisineInfo(
        slug="Brazilian_cuisine",
        title="Brazilian cuisine",
        description=(
            "Brazilian cuisine has European, African and Amerindian influences and varies "
            "greatly by region."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/6/6f/Feijoada_Completa.jpg",
    ),
    _CuisineInfo(
        slug="Mexican_cuisine",
        title="Mexican cuisine",
        description=(
            "Mexican cuisine is one of the world's great cuisines and has a profusion of "
            "different and delicious dishes."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/7/74/Tacos_de_carnitas.jpg",
    ),
    _CuisineInfo(
        slug="Peruvian_cuisine",
        title="Peruvian cuisine",
        description=(
            "Peruvian cuisine is the fusion of different cultures across five continents and "
            "has evolved over the years to become a melting pot of flavours."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/4/4e/Ceviche_peruano.jpg",
    ),
    _CuisineInfo(
        slug="Cuisine_of_Britain_and_Ireland",
        title="British and Irish cuisine",
        description=(
            "British and Irish cuisine is known worldwide for iconic dishes such as fish and "
            "chips or the Full English breakfast, but there is a lot more to explore across "
            "the islands."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/6/62/Traditional_Fish_%26_Chips.jpg",
    ),
    _CuisineInfo(
        slug="French_cuisine",
        title="French cuisine",
        description=(
            "French cuisine is the archetype of the sophisticated metropolitan style of "
            "cooking, and a major influence on almost all cuisines worldwide."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/a/a0/French_cuisine-Flickr-_Alpha.jpg",
    ),
    _CuisineInfo(
        slug="German_cuisine",
        title="German cuisine",
        description=(
            "German cuisine varies by region, but it is best known for sausages, bread and a "
            "wide range of hearty dishes."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/9/92/Sausages_with_mustard_zeltfest_BW_1.jpg",
    ),
    _CuisineInfo(
        slug="Bavarian_cuisine",
        title="Bavarian cuisine",
        description=(
            "In Bavarian cuisine, meat and dumplings in gravy are a staple and these are "
            "accompanied by sauerkraut, knödel, dumplings or spätzle."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/f/f4/BavarianLunch.jpg",
    ),
    _CuisineInfo(
        slug="Franconian_cuisine",
        title="Franconian cuisine",
        description=(
            "Franconian cuisine emphasizes meat and potatoes, as for example the best known "
            "specialties are Bratwürste and Schäufele with potato dumplings."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/5/5e/Brotscheiben_Brotzeit.JPG",
    ),
    _CuisineInfo(
        slug="Georgian_cuisine",
        title="Georgian cuisine",
        description=(
            "Georgian cuisine is very varied. In addition to its many famous meat dishes, "
            "there are also a range of vegetarian and vegan dishes, in part due to the "
            "ubiquitous presence of the Orthodox Church which prescribes frequent 'fasting' "
            "days requiring a form of abstinence close to veganism."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/1/1d/Niko_Pirosmani._Autumn_Feast._Niko_Six_-_picture_Panel._Oil_on_oilcloth._179%2C5X379.jpg",
    ),
    _CuisineInfo(
        slug="Greek_cuisine",
        title="Greek cuisine",
        description=(
            "The Greek cuisine is one of many great Mediterranean cuisines. Greece welcomes "
            "about 30 million visitors every year, and as such many beachgoers and cultural "
            "tourists will also get to know the delicacies of the Greek cuisine."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/6/60/Naxos_Taverna.jpg",
    ),
    _CuisineInfo(
        slug="Italian_cuisine",
        title="Italian cuisine",
        description=(
            "While Italian cuisine is known around the world for dishes such as pizza and "
            "pasta, the domestic cuisine of Italy itself differs a lot from "
            "internationalized Italian dining."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/9/93/Spaghetti_alla_Carbonara.jpg",
    ),
    _CuisineInfo(
        slug="Nordic_cuisine",
        title="Nordic cuisine",
        description=(
            "The cuisines of all Nordic countries are quite similar, although each country "
            "does have its signature dishes."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/9/9b/SwedishSurstr%C3%B6mmingJake73.jpg",
    ),
    _CuisineInfo(
        slug="Finnish_cuisine",
        title="Finnish cuisine",
        description=(
            "The cuisine of Finland is heavily influenced by its neighbours, the main "
            "staples being potatoes and bread with various fish and meat dishes on the side."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/f/f2/Christmas_buffet_at_H%C3%A4meenkyl%C3%A4n_kartano.jpg",
    ),
    _CuisineInfo(
        slug="Portuguese_cuisine",
        title="Portuguese cuisine",
        description=(
            "Portuguese cuisine comes from mainland Europe's westernmost country. "
            "Portugal's Atlantic coast and the Age of Discovery have left their marks on the "
            "nation's cooking."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/9/9a/Cozido_a_portuguesa_1.JPG",
    ),
    _CuisineInfo(
        slug="Russian_cuisine",
        title="Russian cuisine",
        description=(
            "As Russia is the world's largest country by land area, with a long history "
            "through the Russian Empire and the Soviet Union, it has a rich culinary "
            "tradition."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/b/ba/Russian_Cuisine_IMG_2880.JPG",
    ),
    _CuisineInfo(
        slug="Spanish_cuisine",
        title="Spanish cuisine",
        description=(
            "Although less famous than its culinary neighbours to the east or north, Spanish "
            "cuisine is one of the great cuisines of the Mediterranean, and Spaniards are "
            "very proud of their gastronomy."
        ),
        image="https://upload.wikimedia.org/wikipedia/commons/3/34/Tapas_marte%C3%B1as.jpg",
    ),
)


def _build_tip(info: _CuisineInfo) -> Tip:
    base_url = "https://en.wikivoyage.org/wiki/"
    description = _trim(info.description)
    return Tip(
        title=info.title,
        body=description,
        image_url=info.image,
        source_name="Wikivoyage",
        source_url=f"{base_url}{info.slug}",
    )


_CUISINE_TIPS: Tuple[Tip, ...] = tuple(_build_tip(info) for info in _CURATED_CUISINES)


class TipService:
    """Serve cuisine tips in a randomised rotation."""

    def __init__(self, tips: Sequence[Tip] | None = None) -> None:
        self._tips: Tuple[Tip, ...] = tuple(tips) if tips is not None else _CUISINE_TIPS

    async def get_tips(self, *, limit: int = 6) -> List[Tip]:
        """Return a shuffled subset of the curated cuisine tips."""

        if limit <= 0:
            return []

        pool = list(self._tips)
        random.shuffle(pool)
        return pool[: min(limit, len(pool))]


__all__ = ["Tip", "TipService"]
