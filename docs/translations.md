# Translations

SailCast is in English and 11 more languages: German, French, Dutch, Spanish, Simplified Chinese, Italian, Polish, Swedish, Russian, Czech and Brazilian Portuguese. Together they cover about 86% of Home Assistant installs; the [plan](PLAN.md#13-languages) says how they were chosen.

**The 11 translations were written by AI (Claude) in November 2026, and no native speaker has checked them yet.** If you sail and speak one of these languages, corrections are welcome, above all for the safety wording. Open an issue, or a pull request that changes the files below.

## Where the strings are

- `custom_components/sailcast/translations/<code>.json` holds what Home Assistant shows: the setup and options dialogs, entity names and states, repairs and the `get_forecast` action. Its `common` group holds the text SailCast writes itself: calendar events and the notification when a planned sail's forecast gets worse. That text is in the language Home Assistant itself is set to, except an event you add from the panel, which is in yours.
- `frontend/src/translations/<code>.json` holds the panel's strings. The panel follows each person's own language.

The AI summary isn't in these files. The AI provider writes it in the reader's language.

## Rules

1. **Keep every key, and add none.** `python3 scripts/check_translations.py` checks all the languages, or the ones you name (`python3 scripts/check_translations.py de`). CI runs it on every pull request.
2. **Keep every `{placeholder}` exactly as it's written.** Move it wherever your grammar needs it. The check fails if one goes missing or changes.
3. **Safety wording is never softer than the English.** Use the glossary's words for the ratings, boat sizes and skill levels everywhere, so the setup dialogs, the panel and calendar events agree.
4. **Names stay as they are:** SailCast, Home Assistant, NOAA, NDBC, the National Weather Service, Rijkswaterstaat, Kartverket, WorldTides, MeteoAlarm, Open-Meteo, ECMWF IFS, GFS, ICON, OpenStreetMap, OpenSeaMap, OpenFreeMap, Local Calendar, Google Calendar and CalDAV. So do warning names such as Small Craft Advisory, which the services publish in English. Canada's agencies have official French names, which the French translation uses.
5. **Two texts are required by the data's terms and stay in English:** MeteoAlarm's note on delays (`warnings.meteoalarm_note`) and Canada's credit, "Data Source: Environment and Climate Change Canada" (`sources.warnings_by.eccc`). French uses Canada's official French credit, "Source des données : Environnement et Changement climatique Canada".
6. **Units:** wind is always in knots, with your language's abbreviation from the glossary. Where the English gives two units, such as "16 ft (5 m)", keep both. Numbers written into the text use your language's decimal and thousands separators, and times use the 24-hour clock where your language does (the "6 PM" in the automatic calendar texts becomes 18:00).
7. **Home Assistant's menus** are named as Home Assistant's own translation names them. Each language's table below lists them.
8. **Short labels stay short:** `level_short`, the keys ending in `_short`, the `compass` and `weekday` abbreviations, and `size_letter`, which is one letter or character per boat size, each different.
9. **Some strings are pieces of a sentence.** `advice.trend_building` and `trend_easing` follow the wind range, so they start with a comma. `advice.high_tide` and `low_tide` are joined with `advice.list_separator`, and the list's first letter is capitalized. In `common`, `date` puts together a weekday, a day and a month: `weekday_*` are the names as they read inside a sentence, `month_*` the short names as they read after a day number, and `first_of_month` is how a date writes the first, such as "1er" in French. In the panel, `week.day_date` and `week.day_time` put a day's name, a weekday or `week.today`, together with its date or time: use the order and punctuation of your language's dates, such as "samedi 7 nov." or "11月7日 星期六". SailCast writes times itself, on the 12-hour clock in English and the 24-hour clock in the other languages.
10. **Typography:** your language's quotation marks and spacing. Keep "–" in ranges, "·" between items, "→" in menu paths and "…".
11. **Address people** the way Home Assistant does in your language, as the glossary says.

## Glossary

### German (`de`)

| English | Use |
| --- | --- |
| Good (safety rating) | Gut |
| Caution (safety rating) | Vorsicht |
| Not recommended (safety rating) | Nicht empfohlen |
| Dangerous (safety rating) | Gefährlich |
| Great (score band) | Sehr gut |
| Good (score band) | Gut |
| Fair (score band) | Mäßig |
| Poor (score band) | Schlecht |
| Dinghy and beach cat (boat size) | Jolle und Strandkatamaran |
| Small keelboat (boat size) | Kleines Kielboot |
| Cruiser (boat size) | Fahrtenyacht |
| Large cruiser (boat size) | Große Fahrtenyacht |
| Beginner (skill) | Einsteiger |
| Intermediate (skill) | Fortgeschritten |
| Advanced (skill) | Erfahren |
| safety rating | Sicherheitseinstufung |
| score (0–100) | Wertung |
| sailing window | Segelfenster |
| spot (a place you sail) | Revier |
| sailor | Segler |
| boat | Boot |
| official warning | amtliche Warnung |
| advisory (as in Small Craft Advisory) | Warnung |
| sustained wind (the mean, not gusts) | mittlerer Wind |
| gusts | Böen |
| waves | Wellen |
| chop (steep, short waves) | kurze, steile Welle |
| offshore wind (blowing away from the shore) | ablandiger Wind |
| open water upwind (fetch) | freie Wasserfläche in Luv |
| high tide / low tide | Hochwasser / Niedrigwasser |
| flood / ebb / slack (tidal current) | Flutstrom / Ebbstrom / Stauwasser |
| wind against the flood or ebb | Wind gegen den Flut- oder Ebbstrom |
| chart datum | Seekartennull |
| mean sea level | mittlerer Meeresspiegel |
| buoy | Boje |
| marine zone | Seewettergebiet |
| pin (on the map) | Markierung |
| confidence (high, medium, low) | Zuverlässigkeit (hoch, mittel, niedrig) |
| reef (verb) | reffen |
| depower | Segeldruck verringern |
| ease the sheets | Schoten fieren |
| hike (lean out) | ausreiten |
| capsize | kentern |
| mooring | Liegeplatz |
| planned sail (a window in your calendar) | geplanter Törn |
| sunrise / sunset | Sonnenaufgang / Sonnenuntergang |
| kt (knots, after a number) | kn |
| nm (nautical miles, after a number) | sm |
| you (form of address) | du |

Home Assistant's own names, as its German translation has them:

| English | German |
| --- | --- |
| Settings | Einstellungen |
| Devices & services | Geräte & Dienste |
| Configure | Konfigurieren |
| System | System |
| AI | KI |
| Repairs | Reparaturen |
| Notifications | Benachrichtigungen |
| Administrator | Administrator |
| Calendar | Kalender |
| Automations & scenes | Automationen & Szenen |
| Blueprints | Blueprints |
| Import blueprint | Blueprint importieren |

### French (`fr`)

| English | Use |
| --- | --- |
| Good (safety rating) | Bon |
| Caution (safety rating) | Prudence |
| Not recommended (safety rating) | Déconseillé |
| Dangerous (safety rating) | Dangereux |
| Great (score band) | Excellent |
| Good (score band) | Bon |
| Fair (score band) | Moyen |
| Poor (score band) | Médiocre |
| Dinghy and beach cat (boat size) | Dériveur et catamaran de plage |
| Small keelboat (boat size) | Petit quillard |
| Cruiser (boat size) | Voilier de croisière |
| Large cruiser (boat size) | Grand voilier de croisière |
| Beginner (skill) | Débutant |
| Intermediate (skill) | Intermédiaire |
| Advanced (skill) | Confirmé |
| safety rating | niveau de sécurité |
| score (0–100) | note |
| sailing window | créneau de navigation |
| spot (a place you sail) | plan d'eau |
| sailor | marin |
| boat | bateau |
| official warning | alerte officielle |
| advisory (as in Small Craft Advisory) | avis |
| sustained wind (the mean, not gusts) | vent moyen |
| gusts | rafales |
| waves | vagues |
| chop (steep, short waves) | clapot |
| offshore wind (blowing away from the shore) | vent de terre |
| open water upwind (fetch) | fetch (plan d'eau libre au vent) |
| high tide / low tide | pleine mer / basse mer |
| flood / ebb / slack (tidal current) | flot / jusant / étale |
| wind against the flood or ebb | vent contre le flot ou le jusant |
| chart datum | zéro hydrographique |
| mean sea level | niveau moyen de la mer |
| buoy | bouée |
| marine zone | zone marine |
| pin (on the map) | repère |
| confidence (high, medium, low) | fiabilité (élevée, moyenne, faible) |
| reef (verb) | prendre un ris |
| depower | réduire la puissance |
| ease the sheets | choquer les écoutes |
| hike (lean out) | faire du rappel |
| capsize | chavirer |
| mooring | mouillage |
| planned sail (a window in your calendar) | sortie prévue |
| sunrise / sunset | lever / coucher du soleil |
| kt (knots, after a number) | nd |
| nm (nautical miles, after a number) | M |
| you (form of address) | vous |

Home Assistant's own names, as its French translation has them:

| English | French |
| --- | --- |
| Settings | Paramètres |
| Devices & services | Appareils et services |
| Configure | Configurer |
| System | Système |
| AI | IA |
| Repairs | Corrections |
| Notifications | Notifications |
| Administrator | Administrateur |
| Calendar | Calendrier |
| Automations & scenes | Automatisations et scènes |
| Blueprints | Blueprints |
| Import blueprint | Importer un blueprint |

### Dutch (`nl`)

| English | Use |
| --- | --- |
| Good (safety rating) | Goed |
| Caution (safety rating) | Voorzichtig |
| Not recommended (safety rating) | Afgeraden |
| Dangerous (safety rating) | Gevaarlijk |
| Great (score band) | Uitstekend |
| Good (score band) | Goed |
| Fair (score band) | Matig |
| Poor (score band) | Slecht |
| Dinghy and beach cat (boat size) | Jol en strandcatamaran |
| Small keelboat (boat size) | Kleine kielboot |
| Cruiser (boat size) | Kajuitjacht |
| Large cruiser (boat size) | Groot kajuitjacht |
| Beginner (skill) | Beginner |
| Intermediate (skill) | Gevorderd |
| Advanced (skill) | Ervaren |
| safety rating | veiligheidsbeoordeling |
| score (0–100) | score |
| sailing window | zeilvenster |
| spot (a place you sail) | vaargebied |
| sailor | zeiler |
| boat | boot |
| official warning | officiële waarschuwing |
| advisory (as in Small Craft Advisory) | waarschuwing |
| sustained wind (the mean, not gusts) | gemiddelde wind |
| gusts | windstoten |
| waves | golven |
| chop (steep, short waves) | korte, steile golven |
| offshore wind (blowing away from the shore) | aflandige wind |
| open water upwind (fetch) | strijklengte (open water aan loefzijde) |
| high tide / low tide | hoogwater / laagwater |
| flood / ebb / slack (tidal current) | vloed / eb / kentering |
| wind against the flood or ebb | wind tegen de vloed of de eb |
| chart datum | kaartnul |
| mean sea level | gemiddeld zeeniveau |
| buoy | boei |
| marine zone | zeegebied |
| pin (on the map) | speld |
| confidence (high, medium, low) | betrouwbaarheid (hoog, gemiddeld, laag) |
| reef (verb) | reven |
| depower | minder druk op de zeilen zetten |
| ease the sheets | schoten vieren |
| hike (lean out) | uithangen |
| capsize | omslaan |
| mooring | ligplaats |
| planned sail (a window in your calendar) | geplande zeiltocht |
| sunrise / sunset | zonsopkomst / zonsondergang |
| kt (knots, after a number) | kn |
| nm (nautical miles, after a number) | zeemijl |
| you (form of address) | je |

Home Assistant's own names, as its Dutch translation has them:

| English | Dutch |
| --- | --- |
| Settings | Instellingen |
| Devices & services | Apparaten en diensten |
| Configure | Configureer |
| System | Systeem |
| AI | AI |
| Repairs | Reparaties |
| Notifications | Meldingen |
| Administrator | Beheerder |
| Calendar | Agenda |
| Automations & scenes | Automatiseringen en scènes |
| Blueprints | Blueprints |
| Import blueprint | Importeer blueprint |

### Spanish (`es`)

| English | Use |
| --- | --- |
| Good (safety rating) | Bueno |
| Caution (safety rating) | Precaución |
| Not recommended (safety rating) | No recomendado |
| Dangerous (safety rating) | Peligroso |
| Great (score band) | Excelente |
| Good (score band) | Bueno |
| Fair (score band) | Regular |
| Poor (score band) | Malo |
| Dinghy and beach cat (boat size) | Vela ligera y catamarán de playa |
| Small keelboat (boat size) | Velero de quilla pequeño |
| Cruiser (boat size) | Crucero |
| Large cruiser (boat size) | Crucero grande |
| Beginner (skill) | Principiante |
| Intermediate (skill) | Intermedio |
| Advanced (skill) | Avanzado |
| safety rating | valoración de seguridad |
| score (0–100) | puntuación |
| sailing window | ventana de navegación |
| spot (a place you sail) | zona |
| sailor | navegante |
| boat | barco |
| official warning | aviso oficial |
| advisory (as in Small Craft Advisory) | aviso |
| sustained wind (the mean, not gusts) | viento medio |
| gusts | rachas |
| waves | olas |
| chop (steep, short waves) | mar picada |
| offshore wind (blowing away from the shore) | viento terral |
| open water upwind (fetch) | fetch (agua abierta a barlovento) |
| high tide / low tide | pleamar / bajamar |
| flood / ebb / slack (tidal current) | creciente / vaciante / repunte |
| wind against the flood or ebb | viento contra la creciente o la vaciante |
| chart datum | cero hidrográfico |
| mean sea level | nivel medio del mar |
| buoy | boya |
| marine zone | zona marítima |
| pin (on the map) | marcador |
| confidence (high, medium, low) | confianza (alta, media, baja) |
| reef (verb) | tomar rizos |
| depower | quitar potencia |
| ease the sheets | amollar las escotas |
| hike (lean out) | sacar el cuerpo (hacer banda) |
| capsize | volcar |
| mooring | amarre |
| planned sail (a window in your calendar) | salida planificada |
| sunrise / sunset | amanecer / puesta de sol |
| kt (knots, after a number) | kn |
| nm (nautical miles, after a number) | MN |
| you (form of address) | tú |

Home Assistant's own names, as its Spanish translation has them:

| English | Spanish |
| --- | --- |
| Settings | Configuración |
| Devices & services | Dispositivos y servicios |
| Configure | Configurar |
| System | Sistema |
| AI | IA |
| Repairs | Reparaciones |
| Notifications | Notificaciones |
| Administrator | Administrador |
| Calendar | Calendario |
| Automations & scenes | Automatizaciones y escenas |
| Blueprints | Planos |
| Import blueprint | Importar plano |

### Simplified Chinese (`zh-Hans`)

| English | Use |
| --- | --- |
| Good (safety rating) | 良好 |
| Caution (safety rating) | 注意 |
| Not recommended (safety rating) | 不建议 |
| Dangerous (safety rating) | 危险 |
| Great (score band) | 极佳 |
| Good (score band) | 良好 |
| Fair (score band) | 一般 |
| Poor (score band) | 较差 |
| Dinghy and beach cat (boat size) | 稳向板艇和沙滩双体船 |
| Small keelboat (boat size) | 小型龙骨艇 |
| Cruiser (boat size) | 巡航帆船 |
| Large cruiser (boat size) | 大型巡航帆船 |
| Beginner (skill) | 初级 |
| Intermediate (skill) | 中级 |
| Advanced (skill) | 高级 |
| safety rating | 安全评级 |
| score (0–100) | 评分 |
| sailing window | 航行窗口 |
| spot (a place you sail) | 地点 |
| sailor | 帆船手 |
| boat | 船 |
| official warning | 官方预警 |
| advisory (as in Small Craft Advisory) | 预警 |
| sustained wind (the mean, not gusts) | 平均风速 |
| gusts | 阵风 |
| waves | 浪 |
| chop (steep, short waves) | 短促陡浪 |
| offshore wind (blowing away from the shore) | 离岸风 |
| open water upwind (fetch) | 上风开阔水面（风区） |
| high tide / low tide | 高潮 / 低潮 |
| flood / ebb / slack (tidal current) | 涨潮流 / 落潮流 / 憩流 |
| wind against the flood or ebb | 风与涨潮流或落潮流相逆 |
| chart datum | 海图基准面 |
| mean sea level | 平均海平面 |
| buoy | 浮标 |
| marine zone | 海区 |
| pin (on the map) | 图钉 |
| confidence (high, medium, low) | 可信度（高、中、低） |
| reef (verb) | 缩帆 |
| depower | 减小帆力 |
| ease the sheets | 放松帆脚索 |
| hike (lean out) | 压舷 |
| capsize | 翻船 |
| mooring | 系泊处 |
| planned sail (a window in your calendar) | 计划出航 |
| sunrise / sunset | 日出 / 日落 |
| kt (knots, after a number) | 节 |
| nm (nautical miles, after a number) | 海里 |
| you (form of address) | 您 |

Home Assistant's own names, as its Simplified Chinese translation has them:

| English | Simplified Chinese |
| --- | --- |
| Settings | 设置 |
| Devices & services | 设备与服务 |
| Configure | 配置 |
| System | 系统 |
| AI | AI |
| Repairs | 修复 |
| Notifications | 通知 |
| Administrator | 管理员 |
| Calendar | 日历 |
| Automations & scenes | 自动化与场景 |
| Blueprints | 蓝图 |
| Import blueprint | 导入蓝图 |

### Italian (`it`)

| English | Use |
| --- | --- |
| Good (safety rating) | Buono |
| Caution (safety rating) | Attenzione |
| Not recommended (safety rating) | Sconsigliato |
| Dangerous (safety rating) | Pericoloso |
| Great (score band) | Ottimo |
| Good (score band) | Buono |
| Fair (score band) | Discreto |
| Poor (score band) | Scarso |
| Dinghy and beach cat (boat size) | Deriva e catamarano da spiaggia |
| Small keelboat (boat size) | Piccola barca a chiglia |
| Cruiser (boat size) | Cabinato |
| Large cruiser (boat size) | Cabinato grande |
| Beginner (skill) | Principiante |
| Intermediate (skill) | Intermedio |
| Advanced (skill) | Esperto |
| safety rating | valutazione di sicurezza |
| score (0–100) | punteggio |
| sailing window | finestra di navigazione |
| spot (a place you sail) | zona |
| sailor | velista |
| boat | barca |
| official warning | avviso ufficiale |
| advisory (as in Small Craft Advisory) | avviso |
| sustained wind (the mean, not gusts) | vento medio |
| gusts | raffiche |
| waves | onde |
| chop (steep, short waves) | mare corto |
| offshore wind (blowing away from the shore) | vento di terra |
| open water upwind (fetch) | fetch (specchio d'acqua libero sopravvento) |
| high tide / low tide | alta marea / bassa marea |
| flood / ebb / slack (tidal current) | flusso / riflusso / stanca |
| wind against the flood or ebb | vento contro il flusso o il riflusso |
| chart datum | zero idrografico |
| mean sea level | livello medio del mare |
| buoy | boa |
| marine zone | zona marina |
| pin (on the map) | segnaposto |
| confidence (high, medium, low) | affidabilità (alta, media, bassa) |
| reef (verb) | prendere i terzaroli |
| depower | depotenziare le vele |
| ease the sheets | lascare le scotte |
| hike (lean out) | sporgersi fuori bordo |
| capsize | scuffiare |
| mooring | ormeggio |
| planned sail (a window in your calendar) | uscita programmata |
| sunrise / sunset | alba / tramonto |
| kt (knots, after a number) | kn |
| nm (nautical miles, after a number) | NM |
| you (form of address) | tu |

Home Assistant's own names, as its Italian translation has them:

| English | Italian |
| --- | --- |
| Settings | Impostazioni |
| Devices & services | Dispositivi e servizi |
| Configure | Configura |
| System | Sistema |
| AI | IA |
| Repairs | Riparazioni |
| Notifications | Notifiche |
| Administrator | Amministratore |
| Calendar | Calendario |
| Automations & scenes | Automazioni e scenari |
| Blueprints | Progetti |
| Import blueprint | Importa progetto |

### Polish (`pl`)

| English | Use |
| --- | --- |
| Good (safety rating) | Dobre |
| Caution (safety rating) | Uwaga |
| Not recommended (safety rating) | Niezalecane |
| Dangerous (safety rating) | Niebezpieczne |
| Great (score band) | Świetne |
| Good (score band) | Dobre |
| Fair (score band) | Przeciętne |
| Poor (score band) | Słabe |
| Dinghy and beach cat (boat size) | Łódka mieczowa i katamaran plażowy |
| Small keelboat (boat size) | Mały jacht kilowy |
| Cruiser (boat size) | Jacht turystyczny |
| Large cruiser (boat size) | Duży jacht turystyczny |
| Beginner (skill) | Początkujący |
| Intermediate (skill) | Średniozaawansowany |
| Advanced (skill) | Zaawansowany |
| safety rating | ocena bezpieczeństwa |
| score (0–100) | wynik |
| sailing window | okno żeglarskie |
| spot (a place you sail) | akwen |
| sailor | żeglarz |
| boat | łódź |
| official warning | oficjalne ostrzeżenie |
| advisory (as in Small Craft Advisory) | ostrzeżenie |
| sustained wind (the mean, not gusts) | wiatr średni |
| gusts | porywy |
| waves | fale |
| chop (steep, short waves) | krótka, stroma fala |
| offshore wind (blowing away from the shore) | wiatr od lądu |
| open water upwind (fetch) | rozbieg fali (otwarta woda na nawietrznej) |
| high tide / low tide | wysoka woda / niska woda |
| flood / ebb / slack (tidal current) | przypływ / odpływ / zastój |
| wind against the flood or ebb | wiatr przeciwko przypływowi lub odpływowi |
| chart datum | poziom odniesienia mapy |
| mean sea level | średni poziom morza |
| buoy | boja |
| marine zone | akwen prognozy morskiej |
| pin (on the map) | pinezka |
| confidence (high, medium, low) | pewność (wysoka, średnia, niska) |
| reef (verb) | refować |
| depower | zmniejszyć moc żagli |
| ease the sheets | luzować szoty |
| hike (lean out) | wychylać się za burtę |
| capsize | wywrócić się |
| mooring | miejsce postoju |
| planned sail (a window in your calendar) | zaplanowany rejs |
| sunrise / sunset | wschód / zachód słońca |
| kt (knots, after a number) | kn |
| nm (nautical miles, after a number) | Mm |
| you (form of address) | ty (nieformalnie, jak Home Assistant) |

Home Assistant's own names, as its Polish translation has them:

| English | Polish |
| --- | --- |
| Settings | Ustawienia |
| Devices & services | Urządzenia oraz usługi |
| Configure | Konfiguruj |
| System | System |
| AI | AI |
| Repairs | Problemy |
| Notifications | Powiadomienia |
| Administrator | Administrator |
| Calendar | Kalendarz |
| Automations & scenes | Automatyzacje oraz sceny |
| Blueprints | Schematy |
| Import blueprint | Importuj schemat |

### Swedish (`sv`)

| English | Use |
| --- | --- |
| Good (safety rating) | Bra |
| Caution (safety rating) | Försiktighet |
| Not recommended (safety rating) | Avråds |
| Dangerous (safety rating) | Farligt |
| Great (score band) | Utmärkt |
| Good (score band) | Bra |
| Fair (score band) | Måttligt |
| Poor (score band) | Dåligt |
| Dinghy and beach cat (boat size) | Jolle och strandkatamaran |
| Small keelboat (boat size) | Liten kölbåt |
| Cruiser (boat size) | Långfärdsbåt |
| Large cruiser (boat size) | Stor långfärdsbåt |
| Beginner (skill) | Nybörjare |
| Intermediate (skill) | Medelnivå |
| Advanced (skill) | Avancerad |
| safety rating | säkerhetsbedömning |
| score (0–100) | poäng |
| sailing window | seglingsfönster |
| spot (a place you sail) | plats |
| sailor | seglare |
| boat | båt |
| official warning | officiell varning |
| advisory (as in Small Craft Advisory) | varning |
| sustained wind (the mean, not gusts) | medelvind |
| gusts | byar |
| waves | vågor |
| chop (steep, short waves) | krabb sjö |
| offshore wind (blowing away from the shore) | frånlandsvind |
| open water upwind (fetch) | stryklängd (öppet vatten i lovart) |
| high tide / low tide | högvatten / lågvatten |
| flood / ebb / slack (tidal current) | flodström / ebbström / stillvatten |
| wind against the flood or ebb | vind mot flod- eller ebbström |
| chart datum | sjökortets nollnivå |
| mean sea level | medelvattenstånd |
| buoy | boj |
| marine zone | havsområde |
| pin (on the map) | markering |
| confidence (high, medium, low) | tillförlitlighet (hög, medel, låg) |
| reef (verb) | reva |
| depower | minska segeltrycket |
| ease the sheets | släcka på skoten |
| hike (lean out) | hänga ut |
| capsize | kantra |
| mooring | förtöjningsplats |
| planned sail (a window in your calendar) | planerad segling |
| sunrise / sunset | soluppgång / solnedgång |
| kt (knots, after a number) | knop |
| nm (nautical miles, after a number) | NM |
| you (form of address) | du |

Home Assistant's own names, as its Swedish translation has them:

| English | Swedish |
| --- | --- |
| Settings | Inställningar |
| Devices & services | Enheter och tjänster |
| Configure | Konfigurera |
| System | System |
| AI | AI |
| Repairs | Lagningar |
| Notifications | Aviseringar |
| Administrator | Administratör |
| Calendar | Kalender |
| Automations & scenes | Automatiseringar och scener |
| Blueprints | Blueprints |
| Import blueprint | Importera blueprint |

### Russian (`ru`)

| English | Use |
| --- | --- |
| Good (safety rating) | Хорошо |
| Caution (safety rating) | Осторожно |
| Not recommended (safety rating) | Не рекомендуется |
| Dangerous (safety rating) | Опасно |
| Great (score band) | Отлично |
| Good (score band) | Хорошо |
| Fair (score band) | Удовлетворительно |
| Poor (score band) | Плохо |
| Dinghy and beach cat (boat size) | Швертбот и пляжный катамаран |
| Small keelboat (boat size) | Небольшая килевая яхта |
| Cruiser (boat size) | Крейсерская яхта |
| Large cruiser (boat size) | Большая крейсерская яхта |
| Beginner (skill) | Начинающий |
| Intermediate (skill) | Средний уровень |
| Advanced (skill) | Продвинутый |
| safety rating | оценка безопасности |
| score (0–100) | балл |
| sailing window | окно для выхода |
| spot (a place you sail) | акватория |
| sailor | яхтсмен |
| boat | лодка |
| official warning | официальное предупреждение |
| advisory (as in Small Craft Advisory) | предупреждение |
| sustained wind (the mean, not gusts) | средний ветер |
| gusts | порывы |
| waves | волны |
| chop (steep, short waves) | короткая крутая волна |
| offshore wind (blowing away from the shore) | ветер с берега |
| open water upwind (fetch) | разгон волны (открытая вода с наветренной стороны) |
| high tide / low tide | полная вода / малая вода |
| flood / ebb / slack (tidal current) | приливное течение / отливное течение / стояние |
| wind against the flood or ebb | ветер против приливного или отливного течения |
| chart datum | нуль глубин |
| mean sea level | средний уровень моря |
| buoy | буй |
| marine zone | морской район |
| pin (on the map) | метка |
| confidence (high, medium, low) | надёжность (высокая, средняя, низкая) |
| reef (verb) | брать рифы |
| depower | уменьшить тягу парусов |
| ease the sheets | потравить шкоты |
| hike (lean out) | откренивать |
| capsize | перевернуться |
| mooring | стоянка |
| planned sail (a window in your calendar) | запланированный выход |
| sunrise / sunset | восход / закат |
| kt (knots, after a number) | уз |
| nm (nautical miles, after a number) | миль |
| you (form of address) | вы |

Home Assistant's own names, as its Russian translation has them:

| English | Russian |
| --- | --- |
| Settings | Настройки |
| Devices & services | Устройства и службы |
| Configure | Настроить |
| System | Система |
| AI | Искусственный интеллект |
| Repairs | Устранение проблем |
| Notifications | Уведомления |
| Administrator | Администратор |
| Calendar | Календарь |
| Automations & scenes | Автоматизации и сцены |
| Blueprints | Проекты |
| Import blueprint | Импортировать проект |

### Czech (`cs`)

| English | Use |
| --- | --- |
| Good (safety rating) | Dobré |
| Caution (safety rating) | Opatrně |
| Not recommended (safety rating) | Nedoporučeno |
| Dangerous (safety rating) | Nebezpečné |
| Great (score band) | Výborné |
| Good (score band) | Dobré |
| Fair (score band) | Průměrné |
| Poor (score band) | Slabé |
| Dinghy and beach cat (boat size) | Dinghy a plážový katamarán |
| Small keelboat (boat size) | Malá kýlová loď |
| Cruiser (boat size) | Kajutová plachetnice |
| Large cruiser (boat size) | Velká kajutová plachetnice |
| Beginner (skill) | Začátečník |
| Intermediate (skill) | Pokročilý |
| Advanced (skill) | Zkušený |
| safety rating | hodnocení bezpečnosti |
| score (0–100) | skóre |
| sailing window | okno pro plavbu |
| spot (a place you sail) | místo |
| sailor | jachtař |
| boat | loď |
| official warning | oficiální výstraha |
| advisory (as in Small Craft Advisory) | výstraha |
| sustained wind (the mean, not gusts) | průměrný vítr |
| gusts | nárazy větru |
| waves | vlny |
| chop (steep, short waves) | krátké strmé vlny |
| offshore wind (blowing away from the shore) | vítr od břehu |
| open water upwind (fetch) | délka rozběhu (volná voda na návětrné straně) |
| high tide / low tide | vysoká voda / nízká voda |
| flood / ebb / slack (tidal current) | přílivový proud / odlivový proud / stojatá voda |
| wind against the flood or ebb | vítr proti přílivovému nebo odlivovému proudu |
| chart datum | nula map |
| mean sea level | střední hladina moře |
| buoy | bóje |
| marine zone | mořská oblast |
| pin (on the map) | špendlík |
| confidence (high, medium, low) | spolehlivost (vysoká, střední, nízká) |
| reef (verb) | refovat |
| depower | ubrat výkon plachet |
| ease the sheets | povolit otěže |
| hike (lean out) | vysedávat |
| capsize | převrhnout se |
| mooring | kotviště |
| planned sail (a window in your calendar) | plánovaná plavba |
| sunrise / sunset | východ / západ slunce |
| kt (knots, after a number) | kn |
| nm (nautical miles, after a number) | NM |
| you (form of address) | vy |

Home Assistant's own names, as its Czech translation has them:

| English | Czech |
| --- | --- |
| Settings | Nastavení |
| Devices & services | Zařízení a služby |
| Configure | Nastavit |
| System | Systém |
| AI | AI |
| Repairs | Opravy |
| Notifications | Oznámení |
| Administrator | Správce |
| Calendar | Kalendář |
| Automations & scenes | Automatizace a scény |
| Blueprints | Šablony |
| Import blueprint | Importovat šablonu |

### Brazilian Portuguese (`pt-BR`)

| English | Use |
| --- | --- |
| Good (safety rating) | Bom |
| Caution (safety rating) | Atenção |
| Not recommended (safety rating) | Não recomendado |
| Dangerous (safety rating) | Perigoso |
| Great (score band) | Ótimo |
| Good (score band) | Bom |
| Fair (score band) | Razoável |
| Poor (score band) | Ruim |
| Dinghy and beach cat (boat size) | Dinghy e catamarã de praia |
| Small keelboat (boat size) | Veleiro de quilha pequeno |
| Cruiser (boat size) | Veleiro de cruzeiro |
| Large cruiser (boat size) | Veleiro de cruzeiro grande |
| Beginner (skill) | Iniciante |
| Intermediate (skill) | Intermediário |
| Advanced (skill) | Avançado |
| safety rating | classificação de segurança |
| score (0–100) | pontuação |
| sailing window | janela para velejar |
| spot (a place you sail) | local |
| sailor | velejador |
| boat | barco |
| official warning | alerta oficial |
| advisory (as in Small Craft Advisory) | aviso |
| sustained wind (the mean, not gusts) | vento médio |
| gusts | rajadas |
| waves | ondas |
| chop (steep, short waves) | mar picado |
| offshore wind (blowing away from the shore) | vento terral |
| open water upwind (fetch) | pista de vento (fetch) |
| high tide / low tide | maré alta / maré baixa |
| flood / ebb / slack (tidal current) | enchente / vazante / estofo |
| wind against the flood or ebb | vento contra a enchente ou a vazante |
| chart datum | nível de redução |
| mean sea level | nível médio do mar |
| buoy | boia |
| marine zone | área marítima |
| pin (on the map) | marcador |
| confidence (high, medium, low) | confiança (alta, média, baixa) |
| reef (verb) | rizar |
| depower | despotencializar as velas |
| ease the sheets | folgar as escotas |
| hike (lean out) | escorar |
| capsize | emborcar |
| mooring | poita |
| planned sail (a window in your calendar) | velejada planejada |
| sunrise / sunset | nascer / pôr do sol |
| kt (knots, after a number) | nós |
| nm (nautical miles, after a number) | MN |
| you (form of address) | você |

Home Assistant's own names, as its Brazilian Portuguese translation has them:

| English | Brazilian Portuguese |
| --- | --- |
| Settings | Configurações |
| Devices & services | Dispositivos & serviços |
| Configure | Configurar |
| System | Sistema |
| AI | AI |
| Repairs | Reparos |
| Notifications | Notificações |
| Administrator | Administrador |
| Calendar | Calendário |
| Automations & scenes | Automações & cenas |
| Blueprints | Blueprints |
| Import blueprint | Importar blueprint |
