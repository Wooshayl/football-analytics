# Rapport d'avancement — Projet Football Analytics (Ligue 1)

## Objectif du projet

Construire un pipeline de données allant d'un CSV brut d'événements de matchs (scrapé sur WhoScored via la librairie `soccerdata`) jusqu'à une base de données relationnelle propre sur Supabase, exploitée ensuite par une application Streamlit. Le but final : fiches joueurs, comparaisons, classements, visualisations (shot maps, pass maps), et à terme des modèles de machine learning (xG, xA, détection de joueurs similaires).

---

## Étape 1 — Point de départ et diagnostic initial

Le projet partait d'un unique gros CSV (`ligue1_match_events_ml.csv`, ~467 000 lignes, 28 colonnes) contenant tous les événements de tous les matchs de la saison 2025-2026, dans le style des données Opta/WhoScored (une ligne = un événement de jeu : passe, tir, faute, carton...).

Un premier travail avait déjà été fait en amont (hors de cette conversation) : construction de `Players` (551 joueurs) et `Team_Player` (561 lignes, révélant 10 transferts en cours de saison) directement par extraction des colonnes `player_id`/`player` et `team_id`/`team` du CSV brut, avec vérification systématique `shape` vs `nunique()` pour valider chaque table avant de la considérer comme fiable — méthode conservée tout du long du projet.

Un MCD (modèle conceptuel de données) avait été esquissé avec l'aide de ChatGPT, proposant les tables `Team`, `Player`, `Football_match`, `Events`, `Team_player`, `Player_match_stats`. Ce modèle a été validé sur le fond mais corrigé sur plusieurs points : score stocké en deux colonnes `home_score`/`away_score` (INT) plutôt qu'en `VARCHAR`, renommage `team_id`/`team_id_1` en `home_team_id`/`away_team_id`, décision de stocker `qualifiers` en JSONB plutôt que d'exploser une centaine de qualifiers Opta en colonnes séparées, et report de la table `Season` à une V2 (règle retenue : *si une table ne contiendrait qu'une seule ligne aujourd'hui, ne pas la créer maintenant*).

---

## Étape 2 — Construction de la table Football_Match (calendrier, scores, dates)

Le CSV brut ne contenait ni date précise, ni score, ni journée de championnat. Ces informations ont été récupérées en scrapant deux sources via `soccerdata` : le calendrier WhoScored (`schedule`) et FBref (`fbref_schedule`, qui fournit en prime la colonne `week`, la journée de championnat, évitant d'avoir à la recalculer).

**Problème rencontré — 34 matchs perdus au merge.** Le premier merge entre les deux sources (sur un index `game` de la forme `"date Équipe1-Équipe2"`) ne donnait que 272 lignes au lieu des 306 attendues (18 équipes, championnat aller-retour). Diagnostic : FBref utilisait le nom complet "Paris Saint-Germain" tandis que WhoScored abrégeait en "PSG", cassant la correspondance sur ces 34 matchs. Résolu en normalisant le nom sur un des deux côtés avant le merge (`str.replace()` sur le niveau d'index concerné, après un `reset_index()`/`set_index()` puisque `game` faisait partie d'un `MultiIndex`).

**Problème classique rencontré à plusieurs reprises** : l'oubli de réassigner le résultat d'une méthode pandas non-inplace (`.rename()`, `.set_index()` appelés sans `df = df.method(...)`), menant à des `KeyError` en aval. Devenu un réflexe de vérification systématique par la suite.

**Nettoyage final** : suppression des colonnes redondantes (`score` en string, doublon de `home_score`/`away_score` ; `round`, qui ne contenait qu'une seule valeur ; `day`/`time`, dérivables de la date). La date a été convertie du fuseau UTC vers `Europe/Paris` (`.dt.tz_convert()`) avant d'être réduite à une simple date, pour éviter un décalage de jour sur les matchs tardifs. Résultat final : 306 lignes, 9 colonnes, indexées sur `game_id`.

---

## Étape 3 — Exploration de `type` et `qualifiers` (la partie la plus longue)

Avant de construire la table de statistiques joueurs, une phase d'exploration dédiée a été nécessaire pour comprendre deux colonnes du CSV brut :

- **`type`** (39 valeurs distinctes) : le type d'événement (`Pass`, `Goal`, `SavedShot`, `MissedShots`, `ShotOnPost`, `Foul`, `Card`, `Save`, `Claim`, `KeeperPickup`...).
- **`qualifiers`** : une colonne texte représentant une liste de dictionnaires Python (`[{'type': {'displayName': ...}, 'value': ...}]`), à parser avec `ast.literal_eval`, contenant des tags plus fins que `type` seul (assists, passes clés, corners, CSC, etc.).

Un inventaire des `displayName` les plus fréquents (`Counter` sur 424 000+ occurrences) a permis de faire des choix informés plutôt que de deviner :

- **Buts contre son camp (CSC)** : qualifier `OwnGoal`. Point piège identifié et vérifié sur un exemple réel (Marquinhos, but marqué pour le PSG alors qu'il jouait pour le PSG contre son propre camp) : la colonne `team` d'un CSC est l'équipe du **buteur**, pas celle qui en bénéficie au score — il faut inverser l'attribution.
- **Assists** : qualifier `IntentionalGoalAssist`, et non `IntentionalAssist` comme on aurait pu le supposer au premier abord. Vérifié par un test de cohérence : `IntentionalAssist` comptait 7211 occurrences, soit bien plus que le nombre total de buts de la saison (863) — donc impossible que ce soit une "passe ayant mené à un but". `IntentionalGoalAssist` (456 occurrences) était cohérent, et confirmé sur un exemple concret (passe suivie immédiatement d'un but, même match, même minute).
- **Passes clés** : qualifier `KeyPass` ou `ShotAssist` (une passe ayant mené à un tir, qu'il soit cadré ou non).
- **Tirs** : distinction cadré/non cadré/poteau directement via `type` (`SavedShot`+`Goal` = cadré, `MissedShots` = non cadré, `ShotOnPost` = poteau) — l'information n'était pas dans `outcome_type`, qui valait toujours `Successful` pour un tir.
- **Fautes** : chaque faute est loggée deux fois (une par équipe), avec un `outcome_type` opposé. `Unsuccessful` = le joueur a commis la faute ; `Successful` = il l'a obtenue. Vérifié sur un extrait réel.
- **Identification des gardiens** : un joueur est considéré gardien sur un match s'il a au moins un événement `Claim`, `KeeperPickup`, `Punch`, `KeeperSweeper` ou `CrossNotClaimed`. Le type `Save`, pourtant intuitivement lié aux gardiens, a été délibérément exclu de cette identification après un test montrant qu'il donnait en moyenne 6,7 "gardiens" distincts par match (jusqu'à 12) — il capture aussi des actions défensives de joueurs de champ, contrairement aux 5 autres types qui donnaient une moyenne cohérente proche de 1-2 par match.

Décision finale : garder une **seule table** `Player_Match_Stats` pour tous les joueurs (gardiens inclus), plutôt que de la scinder en deux tables — un gardien fait aussi des passes, prend des cartons, etc. Les colonnes spécifiques aux gardiens (`gk_claims`, `gk_pickups`...) restent simplement à 0 pour les joueurs de champ.

---

## Étape 4 — Construction de Player_Match_Stats

Construite par agrégation (`groupby(["player_id", "match_id"])`) de colonnes booléennes calculées ligne à ligne à partir de `type`/`outcome_type`/`qualifiers` (buts, own goals, assists, passes clés, tirs par catégorie, fautes, cartons, hors-jeu, actions gardien).

**Problème rencontré — ligne fantôme `player_id = 0`.** Un `player_id` et un `player` valant `0` (au lieu de `NaN`) est apparu dans les données, correspondant à des événements non attribués côté Lorient. Filtré via `df_raw[df_raw["player_id"] > 0]` avant l'agrégation. Ce même résidu a refait surface plus tard dans `Players` lors de l'enrichissement Transfermarkt, et a dû être filtré une seconde fois.

**`goals_conceded`** calculé après coup par croisement avec `Football_Match` : pour chaque ligne joueur-match, le score de l'équipe adverse selon que le joueur était home ou away.

Vérification finale de cohérence : somme de `goals` (836) + `own_goals` (27) = 863, exactement le nombre total de buts de la saison. Table finale : 9413 lignes, 0 doublon sur `(player_id, match_id)`, 0 valeur manquante.

---

## Étape 5 — Construction d'Events

Décision : `Events` reste la table brute quasiment telle quelle (mêmes colonnes que le CSV d'origine), sans restructuration — les colonnes de calcul temporaires (`is_owngoal`, `is_keypass`, etc.) créées pour construire `Player_Match_Stats` ont été retirées avant export, ainsi que la colonne `qualifiers_parsed` (objet Python, redondante avec `qualifiers` en string).

Principe retenu pour trancher ce qui va dans `Player_Match_Stats` vs ce qui reste dans `Events` : si c'est une statistique sur laquelle on veut trier/filtrer/comparer plusieurs joueurs (ex. nombre de tirs cadrés), elle va en colonne agrégée. Si c'est une donnée positionnelle ou de détail (position exacte d'un tir, angle, futur xG, tir sur le poteau précisément), elle reste dans `Events`, récupérable à la demande pour des visualisations comme une shot map ou une pass map d'un joueur sur un match donné.

**Problème rencontré — `event_id` non unique.** Voulant l'utiliser comme clé primaire SQL, il s'est avéré que `event_id` ne comptait que 1921 valeurs distinctes pour 467 318 lignes, et n'était même pas unique au sein d'un seul match (deux événements sans rapport pouvaient partager le même `event_id`, y compris dans la même période de jeu). Aucun pattern fiable trouvé (ni par match, ni par mi-temps). Solution retenue : génération d'une clé technique `event_pk` (simple numérotation séquentielle de 1 à 467 318), en conservant `event_id`/`related_event_id` à titre informatif mais non garanti unique — limitation connue et documentée plutôt que bloquante.

---

## Étape 6 — Enrichissement de Players avec Transfermarkt

`Players` ne contenait initialement que `player_id` et le nom. L'objectif : ajouter date de naissance, position, valeur marchande.

**Piste explorée et écartée — Reep.** Le registre [`withqwerty/reep`](https://github.com/withqwerty/reep) mappe les identités de joueurs à travers 30+ sources (dont WhoScored et Transfermarkt directement). Testé, mais seulement 81 des 551 joueurs (environ 15%) y étaient trouvés, avec un biais net vers les joueurs ayant eu une carrière internationale (Aubameyang, Giroud, Pogba...) — Reep s'appuie majoritairement sur Wikidata, qui documente mieux les joueurs connus. Conservé comme complément ponctuel, pas comme solution principale.

**Solution retenue — `dcaribou/transfermarkt-datasets`.** Dataset Transfermarkt propre et à jour (37 000+ joueurs), matché par nom avec `Players`.

Difficultés rencontrées et résolues dans l'ordre :
1. Le premier filtre sur la Ligue 1 utilisait la mauvaise colonne (`player_club_domestic_competition_id`, le club **au moment d'une valorisation historique**) plutôt que `current_club_domestic_competition_id` (le club **actuel**), ramenant des joueurs sans rapport avec la Ligue 1 d'aujourd'hui (ex. un joueur actif au Brésil, ou un ancien passage en Ligue 1 remontant à 2012).
2. La table de valorisations contenait plusieurs lignes par joueur (jusqu'à 49, un historique complet de valorisations dans le temps) — réduit à une seule ligne par joueur via tri par date et `groupby().tail(1)`.
3. Un premier filtre correct sur le club actuel donnait encore 2253 joueurs pour 18 clubs (environ 125 par effectif, très supérieur à un effectif pro réel) — piste explorée mais non nécessaire à approfondir, le filtre sur la valorisation la plus récente combiné au matching par nom a suffi à obtenir un résultat exploitable.
4. **Homonymes réels** : deux joueurs distincts partageant exactement le même nom (ex. deux "Ousmane Camara", un à Angers un à Auxerre) généraient des doublons au merge. Résolu en croisant le club WhoScored (via `Team_Player` + `Football_Team`) avec le club Transfermarkt, ne gardant que la ligne où les deux clubs concordent.
5. **Doublons issus des transferts** : les 10 joueurs ayant changé de club en cours de saison (déjà repérés dans `Team_Player`, 561 lignes pour 551 joueurs) généraient une ligne par club dans la table enrichie. Dédupliqués sur `player_id` (`keep="first"`), sans impact puisque les colonnes conservées — position, date de naissance, valorisation — ne dépendent pas du club.
6. La ligne fantôme `player_id = 0` a de nouveau été filtrée à cette étape.

Résultat : 86,2% de matching réussi sur le nom exact (475/551 dans un premier calcul, affiné à ~550 lignes après dédoublonnage). Les non-matchés restants sont principalement des cas d'accents/diacritiques ou de noms non-latins translittérés différemment entre les deux sources (ex. noms coréens). Un passage `rapidfuzz` en fuzzy matching est identifié comme piste d'amélioration future, non bloquante pour la suite du projet.

Table `players_enriched.csv` exportée puis substituée à l'ancien `players.csv` (550 lignes).

---

## Étape 7 — Conversion de qualifiers en JSON valide

La colonne `qualifiers`, telle qu'exportée jusque-là, était une représentation Python (`repr()`, guillemets simples), invalide en JSON strict — bloquante pour un typage `JSONB` en PostgreSQL. Convertie via `ast.literal_eval` puis `json.dumps`, avec vérification systématique de chaque ligne par un vrai parseur JSON avant réexport (0 ligne invalide sur 467 318).

---

## État actuel du pipeline de données

| Fichier | Lignes | Contenu |
|---|---|---|
| `teams.csv` | 18 | Clubs de Ligue 1 |
| `players.csv` (enrichi) | 550 | Joueurs + position, date de naissance, valeur marchande Transfermarkt |
| `team_player.csv` | 561 | Lien joueur ↔ club (transferts inclus) |
| `matches.csv` | 306 | Calendrier, scores, journée |
| `player_match_stats.csv` | 9413 | Statistiques agrégées par joueur et par match |
| `events.csv` | 467 318 | Événements bruts, `qualifiers` en JSON valide, `event_pk` en clé technique |

Le notebook `01_data_cleaner.ipynb` documente l'intégralité de ce pipeline, de la lecture du CSV brut jusqu'à l'export final des 6 tables.

---

## Étape 8 — Conversion finale de qualifiers en JSON valide

La colonne `qualifiers`, telle qu'exportée dans les étapes précédentes, restait une représentation Python (`repr()`, guillemets simples), invalide en JSON strict et donc incompatible avec un typage `JSONB` en PostgreSQL. Convertie via `ast.literal_eval` puis `json.dumps`, avec vérification systématique de chaque ligne par un vrai parseur JSON avant réexport (0 ligne invalide sur 467 318).

---

## Étape 9 — Mise en place de Supabase et création du schéma SQL

Projet Supabase créé (région Paris, plan Free, Data API activée, RLS automatique activée par défaut sur les nouvelles tables). Les 6 tables ont été créées via `CREATE TABLE` dans le SQL Editor, dans l'ordre imposé par les dépendances de clés étrangères : `football_team` et `players` (aucune dépendance), puis `football_match` (référence `football_team`), `team_player` (référence les deux précédentes, clé primaire composite `(team_id, player_id)`), `player_match_stats` (référence les trois précédentes, clé composite `(player_id, match_id)`), et enfin `events` (la plus riche, avec `qualifiers` en `JSONB`).

**Décision retenue pour `event_id`**, cohérente avec le problème identifié à l'étape 5 : la table `events` utilise `event_pk` (généré côté pandas) comme véritable clé primaire, `event_id` étant conservé sans contrainte d'unicité, à titre informatif seulement.

---

## Étape 10 — Import des données et problèmes rencontrés

**Renommage de colonnes nécessaire avant import.** Les noms de colonnes des CSV ne correspondaient pas tous exactement aux noms définis dans le schéma SQL : `team` → `team_name`, `player` → `player_name` (uniquement sur `players.csv`, `events.csv` garde `team`/`player` tels quels côté SQL), `week` → `matchday`, suppression des colonnes `round`/`day`/`time` restées dans `matches.csv` malgré une décision de suppression antérieure, et suppression de la colonne `game_id` redondante avec `match_id` dans `events.csv`.

**Problème récurrent — colonnes entières exportées en `float64` à cause des valeurs manquantes.** Toute colonne destinée à être un `INT`/`BIGINT` en SQL mais contenant des `NaN` côté pandas (ex. `player_id` sur les événements sans joueur, `transfermarkt_id` pour les joueurs non matchés) est automatiquement stockée en `float64` par pandas, ce qui donne des valeurs du type `"348654.0"` à l'export CSV — rejetées par Postgres avec l'erreur `invalid input syntax for type integer`. Corrigé en convertissant ces colonnes au type `Int64` (I majuscule, le type entier nullable de pandas, distinct du `int64` natif) avant export. Point important découvert en cours de route : **ce typage `Int64` ne survit pas à un aller-retour par CSV** — relire un CSV avec `pd.read_csv()` fait retomber les colonnes en `float64` même si elles avaient été correctement typées avant l'export précédent. La conversion `Int64` a donc dû être répétée directement dans le script d'import Python, juste après la lecture du CSV, plutôt que de compter sur le fichier lui-même pour la conserver.

**Import via l'interface web Supabase limité en taille de fichier.** Les tables `players`, `football_team`, `football_match` et `team_player` (fichiers de quelques centaines de Ko à quelques Mo) se sont importées sans problème via l'interface Table Editor. `events.csv` (467 318 lignes, 226 Mo) a échoué à deux reprises via cette méthode (import interrompu autour de 3800 puis 146 504 lignes), très probablement à cause d'une limite de taille de fichier côté interface web (l'ordre de grandeur de 50 Mo a été évoqué) combinée à une possible interruption liée à la navigation hors de la page pendant l'upload.

**Solution retenue — import par lots via `supabase-py` en Python.** Script utilisant `create_client()` et des insertions par paquets de 5000 lignes (`batch_size`), avec suivi de progression affiché à chaque lot. Plusieurs obstacles rencontrés et résolus dans l'ordre :
1. **`NaN` invalide en JSON** : `df.where(pd.notnull(df), None)` ne fonctionne pas tel quel sur des colonnes `float64`, car un tableau numpy ne peut pas stocker de `None` — la valeur est silencieusement reconvertie en `NaN`, qui n'est pas un JSON valide (`ValueError: Out of range float values are not JSON compliant: nan`). Corrigé en forçant `.astype(object)` avant le remplacement, pour que `None` soit réellement conservé tel quel.
2. **Permissions RLS bloquant l'écriture.** La clé `anon`/`publishable` n'ayant volontairement que des droits de lecture (policies `SELECT` créées uniquement), l'insertion via cette clé a échoué (`permission denied for table events`). Résolu en utilisant la clé `service_role`/`secret` (qui contourne RLS) pour ce script d'import ponctuel uniquement — jamais utilisée côté application. Un `GRANT SELECT, INSERT ON public.events TO service_role` a aussi été nécessaire, RLS n'exemptant pas automatiquement `service_role` des droits de base au niveau table.
3. **Résidu `player_id = 0` et `related_player_id = 0`**, le même fantôme de données déjà rencontré à plusieurs reprises dans le projet (voir étapes 4 et 6), cette fois bloquant l'import via une violation de contrainte de clé étrangère (`Key (related_player_id)=(0) is not present in table "players"`). Corrigé en remplaçant ces valeurs `0` par `NA` (`pd.NA`) plutôt que de supprimer les lignes concernées — l'événement reste valide, seul le lien vers un joueur devient nul, cohérent avec le traitement déjà appliqué aux événements sans joueur (`Start`, `End`...).
4. **Reprise sur erreur sans tout réimporter.** Grâce au `batch_size` et au suivi de progression affiché, l'import interrompu à 340 000/467 318 lignes a pu reprendre exactement à ce point (`start = 340000` dans la boucle) après correction du problème de données, sans nécessiter de réinsérer les lots déjà passés avec succès ni de vider la table.

**Nettoyage de sécurité post-import.** Les droits d'écriture temporairement accordés à `anon` (`GRANT INSERT ... TO anon` et la policy associée) ont vocation à être retirés une fois l'import définitivement validé, afin que la clé publique utilisée par l'application Streamlit ne conserve que des droits de lecture.

---

## État actuel — validation finale

Tests de cohérence exécutés directement en SQL pour valider la base de bout en bout :
- Comptage des 6 tables conforme aux volumes attendus (18 / 550 / 306 / 560 / 9413 / 467 318).
- Une jointure à trois tables (`player_match_stats` ⋈ `players` ⋈ `football_team`) fonctionne correctement (test effectué sur les buteurs du club WhoScored nommé "PSG" — à noter que `teams.csv`, extrait directement de WhoScored, conserve cette abréviation, contrairement au nom complet "Paris Saint-Germain" utilisé côté FBref lors du merge des calendriers à l'étape 2 ; les deux sources n'ont jamais eu besoin d'être harmonisées entre elles au niveau de `football_team`, chaque table restant cohérente avec sa propre source d'origine).
- Une requête JSONB sur `qualifiers` (recherche d'un `OwnGoal`) retourne des résultats exploitables, confirmant que le typage JSONB est fonctionnel.
- Aucun résidu `player_id = 0` ou `related_player_id = 0` ne subsiste dans `events`.

---

## Mise en ligne sur GitHub

Le projet a été initialisé avec Git et poussé sur un dépôt GitHub (`Wooshayl/football-analytics`). Point de vigilance appliqué avant le premier commit : exclusion de `data/raw/*.csv` et `data/processed/*.csv` du suivi Git (le fichier `events.csv` à lui seul pèse 226 Mo, largement au-dessus de la limite de 100 Mo imposée par GitHub, et l'ensemble des CSV `processed/` est de toute façon intégralement reproductible à partir des données brutes et du notebook `01_data_cleaner.ipynb`, donc sans intérêt à versionner). Le fichier `.env` contenant les clés Supabase a également été vérifié comme exclu avant chaque commit.

---

## Prochaine étape

Nettoyage final des droits temporaires accordés à `anon` sur `events`, puis démarrage de l'application Streamlit : structure multi-pages, connexion à Supabase via la clé `publishable` (lecture seule), et premières pages (fiches joueurs, classements, visualisations).
