// ==UserScript==
// @name         ALIGN Bande Live
// @namespace    align-live
// @version      12.2.14
// @description  Bande du live ALIGN sur TradingView : messages Telegram, bulles, télécommande 15 s, infobulles roses
// @match        https://*.tradingview.com/chart/*
// @updateURL    https://raw.githubusercontent.com/adelkhatra-bit/trading-align-/main/docs/live/align-bande-live.user.js
// @downloadURL  https://raw.githubusercontent.com/adelkhatra-bit/trading-align-/main/docs/live/align-bande-live.user.js
// @run-at       document-idle
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      ntfy.sh
// ==/UserScript==
(function () {
  'use strict';
  if (window.__ALIGN_BANDE__) { try { window.__ALIGN_BANDE__.stop(); } catch (e) {} }
  const VERSION = '12.2.14';  // v12.2.14 : relecture vocale du dernier commentaire IA visible sur activation. v12.2.13 : synchronisation bouche ALIGN LIVE avec le coach vocal. v12.2.12 : voix naturelle retentée quand les voix navigateur arrivent, ON réinitialisé après rechargement et listener nettoyé. v12.2.11 : heartbeat écran via GM_xmlhttpRequest (hors page, sans blocage CORS/réseau). v12.2.10 : la voix garde sa phrase en mémoire jusqu'à la fin (plus de coupure après 2-3 mots). v12.2.9 : libellé « COACH VOCAL OFF » (plus « ACTIVER LE COMMENTATEUR »). v12.2.8 : une seule voix (naturelle), off = silence total, plus de phrase d'accueil. v12.2.7 : la voix parle en français PUIS en anglais (chaque info), voix naturelle si disponible, jamais « risque »  // v12.2.6 : la voix ne lit ni disclaimer ni appel « lien en bio », ni phrase coupée  // v12.2.5 : la voix suit uniquement le commentaire IA visible ; commandes déplacées en bas à gauche  // v12.0 : les commentaires IA du live déclenchent immédiatement bulle, ping prix et lueur neutre  // v11.8 : narration marché calée à 55 s, au plus près du cooldown d'affichage de 52 s  // v11.7 : narration technique factuelle toutes les ~75 s, horloges séparées et activation vocale explicite  // v10.8 : commentaires IA ancrés sur les données réelles du marché affiché  // v10.7 : « ÇA PLONGE 🌊 » quand ça coule (en plus de la fusée) ; v10.6 : NEWS DE DERNIÈRE MINUTE prioritaire (coupe la bande) ; v10.5 : fusée 🚀 + sourire quand le bot entre / quand ça accélère ; v10.4 : bot en position = blagues taquines (je suis dedans avec vous, qui est rentré ? tapote, partage) ; v10.3 : blagues quand le marché dort (petit film, café, ouvertures, tapote MDR) ; v10.2 : « prépare-toi ≠ vas-y 😝 » ; v10.1 : l'animateur remet gentiment les petits malins à leur place (feu vert, discipline 😝) ; v10.0 : après un TP → « une rose ou un like » + « crée ton compte démo » ; v9.9 : fenêtre « 💰 ALIGN EN DIRECT » (gain réel en cours, après la moitié du chemin vers le TP1) ; v9.8 : « active ton coach en temps réel » + « un clic sur Mon bot pour arrêter » ; v9.7 : texte de la ligne du bas plus gros (taille des %) ; v9.6 : ligne du bas qui clignote vert ▲ LONG ? / rouge ▼ SHORT ? (plus vite quand une entrée approche) ; v9.5 : ligne du bas du tableau rouge ↔ vert en boucle + « LONG OU SHORT ? » (le sens ne se voit plus) ; v9.4 : « crée ton compte démo, teste gratuitement » + codes prop firms (lien en bio) ; v9.3 : titres de bulle drôles liés au marché (fin de « LE GRAPH BALANCE ») ; v9.2 : plus de spectacle quand le marché hésite (l'animateur parle toutes les ~40 s, discussion avis → merci → lien en bio), bulle « 🤫 PSST… LE GRAPH BALANCE » ; v9.1 : plus aucune flèche ni sens (monter / baisser) sur la bande ; v9.0 : « tu préfères BTC, Gold ou NASDAQ ? une autre unité de temps ? lien en bio » ; v8.9 : « ALIGN est dedans depuis le début… trop tard pour rentrer, on ne court jamais après le prix » ; v8.8  // v8.8 : l'animateur parle toutes les ~90 s (humour, nouveaux arrivants, commentaires), feu d'artifice « objectif de likes atteint » ; v8.7  // v8.7 : « je t'avais prévenu » après le chrono de grosse distribution / accumulation ; v8.6  // v8.6 : marché calme → l'animateur (vrai trader) parle aux spectateurs : questions rebond / cassure, pression pour taper et commenter ; v8.5  // v8.5 : phrases IA gratuites toujours nouvelles (FR/EN), chrono « une position arrive » + agenda (discours, annonces, ouvertures) venant du bot, chrono posé AU-DESSUS des colonnes 1 min / 3 min / 5 min ; v8.4   // v8.4 : ligne du bas du tableau revenue à sa couleur d'origine (v8.2), texte 13 px ; v8.3  // v8.3 : (étiquettes posées par-dessus désactivées, à faire dans le Pine), ligne du bas du tableau en couleur neutre, plus grosse, « tu peux rentrer ? 👍 » ; v8.2  // v8.2 : prix cachés dans la ligne du bas du tableau (❓ + lien en bio) ; v8.1  // v8.1 : les pastilles de motivation descendent juste au-dessus du tableau des unités (petit écran TikTok), les infos du marché restent collées au prix ; v8.0  // v8.0 : boost du live tout de suite + feu d'artifice, « t'as envie de rentrer là ? », on fait commenter (ça monte ou ça descend ?) ; v7.9  // v7.9 : une fenêtre TradingView ouverte passe DEVANT la bande (on peut toujours la fermer) + la pub « sans publicité » se ferme toute seule ; v7.8  // v7.8 : la pastille suit la langue de la bande (FR/EN) ; v7.7  // v7.7 : pastilles sur 2 lignes collées au prix, animations +12 %, « tapote au lieu de regarder », plus de doublons après réinjection ; v7.6  // v7.6 : le marché PARLE (bulle près du prix, ping sur le prix, texte qui s'écrit), plus de « péter / explosion / branche » ; v7.5 : zones cliquables, plus de contre-sens, pastilles côté prix (haut si ça baisse, bas si ça monte), « connecté depuis ton portable »
  // v7.2 : bandes du haut un peu plus grosses (86 px, texte 40 px)
  const SUJET = 'align-live-2a4bccafd9548d93';
  const BASE = [
    '🟢 LIVE ALIGN 24/7 • BTC • GOLD',
    '👉 ABONNE-TOI • PARTAGE • TAPOTE L\'ÉCRAN',
    '🔗 LIEN EN BIO : COACH EN DIRECT',
    '📲 CONNECTÉ AU MARCHÉ EN TEMPS RÉEL DEPUIS TON PORTABLE • chaque bougie expliquée en direct • lien en bio 🎁',
    '🧭 CHEZ ALIGN ON NE VA JAMAIS CONTRE LA TENDANCE • on suit le marché, on ne le combat pas 💪',
    '⚠️ CECI N\'EST PAS UN CONSEIL EN INVESTISSEMENT • fais tes propres recherches (DYOR)',
    '⚠️ NOT FINANCIAL ADVICE • do your own research (DYOR)',
    '📲 Le coach ALIGN en direct • lien en bio 🎁 gratuit',
    '📲 RESTE CONNECTÉ • CONNECTE-TOI : LIEN EN BIO 🎁',
    '🎁 TOUTES LES POSITIONS SONT GRATUITES • les annonces arrivent en temps réel sur ton portable • lien en bio',   // v7.6 (demande d'Adel)
    '📢 ANNONCE À VENIR… 😏 tu veux savoir avant que ça parte ? • lien en bio 🎁',
    '⚡ UNE ENTRÉE SE PRÉPARE • attends le feu vert, ne cours pas après le prix • lien en bio',
    '🔔 ACTIVE TES NOTIFICATIONS • lien en bio : on te prévient dès que le marché se prépare 🎁',
    '📩 VA DANS LE LIEN EN BIO • tu reçois l\'alerte en temps réel sur le marché, avec les détails et les news 🎁',   // v7.3 : l'avantage de venir chez nous
    '🤖 ACTIVE TON COACH EN TEMPS RÉEL • il entre avec le bot, te suit jusqu\'au TP et t\'envoie toutes les news • gratuit • lien en bio 🎁',   // v9.8 (demande d'Adel)
    '⏸ PLUS ENVIE DE POSITIONS ? UN SEUL CLIC SUR « MON BOT » ET TU ARRÊTES • tu reprends quand tu veux • lien en bio',
    '🆓 CRÉE TON COMPTE DÉMO ET TESTE GRATUITEMENT • zéro risque pour te faire la main 😉 • positions gratuites • lien en bio • ce n\'est pas un conseil en investissement (DYOR)',   // v9.4 (demande d'Adel)
    '🏦 ENVIE DE TRADER AVEC LE CAPITAL D\'UNE PROP FIRM ? codes promo Topstep / FundedNext dans le lien en bio 🎟 • commence par la démo 😉 • ce n\'est pas un conseil en investissement',
    '⚠️ Le trading comporte un risque élevé de perte en capital • Contenu à caractère informatif et éducatif uniquement, qui ne constitue ni un conseil en investissement ni une recommandation personnalisée • Les performances passées ne préjugent pas des performances futures',
    // v6.4 : la même bande en anglais (FR + EN pour toucher tout le monde)
    '👉 FOLLOW • SHARE • TAP THE SCREEN',
    '🔗 LINK IN BIO: LIVE COACH',
    '📲 STAY CONNECTED • CONNECT: LINK IN BIO 🎁',
    '🎁 ALL POSITIONS ARE FREE • announcements land in real time on your phone • link in bio',
    '📢 ANNOUNCEMENT COMING… 😏 want to know before it moves? • link in bio 🎁',
    '⚡ A SETUP IS FORMING • wait for confirmation, never chase price • link in bio',
    '📩 GO TO THE LINK IN BIO • get real-time market alerts with the details and the news 🎁',
    '🔔 TURN ON YOUR NOTIFICATIONS • link in bio: we\'ll tell you as soon as the market gets ready 🎁',
    '📲 CONNECTED TO THE MARKET IN REAL TIME FROM YOUR PHONE • every candle explained live • link in bio 🎁',
    '🧭 AT ALIGN WE NEVER TRADE AGAINST THE TREND • we follow the market, we don\'t fight it 💪',
    '⚠️ Trading involves a high risk of capital loss • Informational and educational content only, it is neither investment advice nor a personalised recommendation • Past performance is not indicative of future results'
  ];
  // v6.4 : traduction anglaise des messages de la bande (chaque info passe en FR puis en EN)
  const EN = [
    ['La tendance récente reste orientée à la hausse, mais les dernières bougies corrigent. Les acheteurs doivent défendre leur mouvement ; on attend une clôture avant de conclure.', 'The recent trend still points higher, but the latest candles are pulling back. Buyers need to defend the move; we wait for a candle close before drawing conclusions.'],
    ['Le mouvement de fond reste orienté à la baisse, mais le marché tente un rebond. Les vendeurs doivent encore montrer s’ils gardent la main ; aucune anticipation.', 'The broader move remains lower, but the market is attempting a rebound. Sellers still need to show whether they remain in control; no guessing ahead.'],
    ['Les acheteurs gardent l’avantage sur les dernières bougies. Je surveille si l’impulsion se prolonge ou si le marché commence à souffler.', 'Buyers have the edge in the latest candles. I’m watching whether momentum continues or the market starts to cool off.'],
    ['Les vendeurs gardent la pression sur les dernières bougies. Je surveille si la baisse continue ou si les acheteurs commencent à réagir.', 'Sellers are applying pressure in the latest candles. I’m watching whether the decline continues or buyers begin to respond.'],
    ['Le marché se resserre : les bougies perdent de l’amplitude et les deux camps attendent. La prochaine clôture aidera à départager acheteurs et vendeurs.', 'The market is tightening: candle ranges are shrinking and both sides are waiting. The next close should help show whether buyers or sellers take control.'],
    ['Le marché évolue en range : acheteurs et vendeurs se neutralisent pour le moment. Je surveille une sortie confirmée plutôt que de deviner le prochain mouvement.', 'The market is ranging: buyers and sellers are balanced for now. I’m watching for a confirmed breakout instead of guessing the next move.'],
    ['Le prix travaille le haut de sa zone récente : attention à une réaction ou à une cassure confirmée.', 'Price is testing the top of its recent range: watch for a reaction or a confirmed breakout.'],
    ['Le prix travaille le bas de sa zone récente : attention à une réaction ou à une cassure confirmée.', 'Price is testing the bottom of its recent range: watch for a reaction or a confirmed breakdown.'],
    ['Le volume est nettement supérieur à sa moyenne récente.', 'Volume is clearly above its recent average.'],
    ['pas de panique • le marché respire, il est comme vous 😅 • patience, la suite en temps réel', 'don\'t panic • the market is breathing, just like you 😅 • patience, what\'s next live'],
    ['le marché prépare quelque chose', 'the market is preparing something'], ['la suite en temps réel', 'what\'s next, live'],
    ['infos en temps réel', 'live info'], ['plus d\'infos en temps réel', 'more live info'], ['plus d\'infos', 'more info'],
    ['connecte-toi au marché depuis ton portable', 'connect to the market from your phone'], ['branche-toi au marché', 'plug into the market'],
    ['Ton portable connecté au marché en temps réel : chaque bougie expliquée en direct', 'Your phone connected to the market in real time: every candle explained live'],
    ['Connecté au marché depuis ton portable : le coach lit chaque bougie avec toi', 'Connected to the market from your phone: the coach reads every candle with you'],
    ['CHANGEMENT DE PROGRAMME', 'CHANGE OF PLAN'], ['le marché a changé d\'avis', 'the market changed its mind'], ['on suit le marché, on ne le combat pas', 'we follow the market, we don\'t fight it'], ['lien en bio', 'link in bio'], ['abonne-toi, partage', 'follow, share'],
    ['abonne-toi', 'follow'], ['partage', 'share'], ['la team', 'team'], ['pas de panique', 'don\'t panic'], ['pourquoi ?', 'why?'],
    ['COMPTE À REBOURS sur', 'COUNTDOWN on'], ['GROSSE DISTRIBUTION', 'BIG SELL-OFF'], ['GROSSE ACCUMULATION', 'BIG ACCUMULATION'],
    ['min max', 'min max'], ['dans', 'in'], ['ÇA ACCÉLÈRE', 'IT\'S SPEEDING UP'], ['jusqu\'où ?', 'how far?'], ['ÇA CASSE', 'BREAKOUT'],
    ['dernier plus bas cassé', 'last low broken'], ['dernier plus haut cassé', 'last high broken'], ['ça peut couler encore…', 'it can drop further…'],
    ['ça peut décoller…', 'it can take off…'], ['LES BALEINES BOUGENT sur', 'WHALES ARE MOVING on'], ['gros volume', 'big volume'],
    ['quelque chose se prépare', 'something is brewing'], ['LA PRESSION MONTE sur', 'PRESSURE IS BUILDING on'], ['MANIPULATION sur', 'MANIPULATION on'],
    ['les gros piègent les acheteurs… la belle distribution', 'big players trap the buyers… the sell-off'],
    ['les gros piègent les vendeurs… le rechargement', 'big players trap the sellers… the reload'],
    ['ANNONCÉ !', 'CALLED IT!'], [' a coulé ', ' dropped '], [' a décollé ', ' took off '], ['la team ALIGN l\'a vu venir', 'team ALIGN saw it coming'],
    ['REBOND sur une ligne clé', 'BOUNCE on a key level'], ['arrive sur une zone clé', 'reaches a key zone'], ['Zone clé du marché', 'Key market zone'],
    ['ce qu\'elle annonce', 'what it means'],
    ['À toi de jouer :', 'Your turn:'], ['va MONTER 📈 ou DESCENDRE 📉 ? Écris-le en commentaire, on verra qui a raison 😏', 'going UP 📈 or DOWN 📉? Write it in the comments, we\'ll see who\'s right 😏'],
    ['Sondage express :', 'Quick poll:'], ['⬆️ ou ⬇️ dans 15 min ? Commente « haut » ou « bas »', '⬆️ or ⬇️ in 15 min? Comment "up" or "down"'],
    ['Les meilleurs pronostics en commentaire…', 'Best predictions in the comments…'], ['continue ou retrace ? Montre que t\'as le flair', 'keeps going or pulls back? Show your instinct'],
    ['Celui qui devine la prochaine bougie de', 'Whoever guesses the next candle of'], ['gagne… notre respect éternel', 'wins… our eternal respect'], ['commente !', 'comment!'],
    ['touche son dernier plus haut', 'hits its last high'], ['touche son dernier plus bas', 'hits its last low'], ['t\'as envie de rentrer là ?', 'tempted to jump in here?'],
    ['Ça continue ou ça retrace ?', 'Keeps going or pulls back?'], ['dis-le en commentaire', 'say it in the comments'], ['le scénario complet est déjà prêt', 'the full scenario is already set'],
    ['MERCI', 'THANKS'], ['BOOSTE LE LIVE', 'BOOSTS THE LIVE'], ['ABONNE-TOI • PARTAGE', 'FOLLOW • SHARE'],
    ['Au lieu de regarder sans rien faire… le marché n\'a pas encore de point d\'entrée 😅 tapote l\'écran pour le réveiller', 'Instead of just watching… the market has no entry point yet 😅 tap the screen to wake it up'],
    ['Pas d\'entrée pour l\'instant : la team patiente… toi tu tapotes, nous on surveille', 'No entry for now: the team waits… you tap, we watch'], ['Zone clé : le marché pourrait y souffler… ce qu\'il prépare', 'Key zone: the market may pause here… what\'s next'],
    ['Zone clé : le marché teste la patience de tout le monde…', 'Key zone: the market is testing everyone\'s patience…'],
    ['BOUGIE 15 MIN CLÔTURÉE', '15 MIN CANDLE CLOSED'], ['Clôture 15 min dans', '15 min close in'], ['c\'est elle qui décide', 'it decides everything'],
    ['veut remonter… jusqu\'où ? le coach le sait', 'wants to bounce… how far? the coach knows'], ['reprend des forces', 'is regaining strength'],
    ['le marché pourrait remonter', 'the market could go up'], ['Les acheteurs reviennent sur', 'Buyers are back on'],
    ['sous pression… va-t-il couler ? réponse en temps réel', 'under pressure… will it drop? live answer'],
    ['Les vendeurs tiennent', 'Sellers are holding'], ['ça peut encore descendre', 'it can still go down'],
    ['glisse… le coach surveille chaque bougie', 'is sliding… the coach watches every candle'],
    ['se compresse… avant le gros mouvement ? ⚡ tiens-toi prêt', 'is squeezing… before the big move? ⚡ get ready'],
    ['hésite… la prochaine clôture peut tout décider', 'hesitates… the next close can decide everything'],
    ['est posé sur une zone clé en bas', 'sits on a key zone below'], ['rebond ou cassure ?', 'bounce or break?'],
    ['teste le bas de sa zone… les acheteurs vont-ils tenir ?', 'tests the bottom of its zone… will buyers hold?'],
    ['touche le haut de sa zone', 'touches the top of its zone'], ['cassure ou rejet ?', 'break or rejection?'],
    ['bute sous un plafond… les vendeurs vont-ils frapper ?', 'is stuck under a ceiling… will sellers strike?'],
    ['au milieu de sa zone : il cherche sa direction… le coach te dit quand ça part', 'in the middle of its zone: looking for direction… the coach tells you when it moves'],
    ['en équilibre : acheteurs et vendeurs se regardent… qui va craquer ?', 'in balance: buyers and sellers stare each other down… who breaks first?'],
    ['Le lien en bio = ton câble branché sur le marché : chaque bougie expliquée en direct', 'The link in bio = your cable plugged into the market: every candle explained live'],
    ['Comme si tu étais connecté au marché : le coach lit chaque bougie avec toi', 'Like being wired to the market: the coach reads every candle with you'],
    ['Tu vois les bougies, le coach te dit ce qu\'elles préparent', 'You see the candles, the coach tells you what they\'re preparing'],
    ['Ressens le marché en direct : pression, pièges, accélérations… tout est dans le', 'Feel the market live: pressure, traps, accelerations… it\'s all in the'],
    ['objectif TOUCHÉ', 'target HIT'], ['On protège', 'We protect'], ['risque zéro', 'zero risk'], ['ÇA ENCAISSE', 'CASHING IN'],
    ['PASSE À L\'ACTION sur', 'TAKES ACTION on'], ['rejoint la team ALIGN, viens nous rejoindre', 'joined team ALIGN, come join us'],
    ['prépare-toi', 'get ready'], ['ça peut couler', 'it may drop'], ['ça peut décoller', 'it may take off'], ['verdict dans', 'verdict in'],
    ['Astuce', 'Tip'], ['Le trading comporte un risque de perte', 'Trading involves a risk of loss'], ['gratuit', 'free'], ['en direct', 'live'],
    ['Bravo à ceux qui ont suivi', 'Well done to everyone who followed'], ['Abonne-toi', 'Follow'], ['ABONNE-TOI', 'FOLLOW'],
    ['protection touché', 'protection hit'], ['on coupe petit, on va se refaire', 'we cut small, we\'ll bounce back'],
    ['objectif frôlé à un cheveu', 'target missed by a hair'], ['petit recul, on garde le cap', 'small pullback, we stay on course'],
    ['ça devrait reprendre', 'it should resume'], ['clôture dans', 'close in'], ['le coach l\'a déjà annoncé', 'the coach already called it'],
    ['JEU : tapote l\'écran si tu penses que', 'GAME: tap the screen if you think'], ['va couler', 'will drop'], ['va monter', 'will rise'],
    ['réponse dans', 'answer in'], ['les niveaux en privé', 'levels in private'], ['Le coach ALIGN', 'The ALIGN coach'],
    ['risque de perte, pas un conseil', 'risk of loss, not advice'],
    ['Ceci n\'est pas un conseil en investissement, fais tes propres recherches (DYOR)', 'This is not financial advice, do your own research (DYOR)'],
    ['WAOUH, ÇA ACCÉLÈRE sur', 'WOW, IT\'S SPEEDING UP on'], ['WAOUH, ÇA PLONGE sur', 'WOW, IT\'S DIVING on'], ['le marché dévale la pente', 'the market is sliding down the slope'], ['le marché prend de la vitesse', 'the market is picking up speed'], ['prochaine clôture dans', 'next close in'],
    ['on encaisse TOUT, le gain est dans la poche', 'we cash out EVERYTHING, the profit is in the pocket'], ['le marché veut revenir… on l\'attend au tournant', 'the market wants to come back… we\'re waiting for it'],
    ['il est revenu, comme prévu', 'it came back, as planned'], ['deuxième service, on reprend la même', 'second round, we take the same one again'],
    ['🌹 LA TEAM VIENT D\'ENCAISSER ! si t\'as kiffé, une petite rose ou un like ❤️ ça motive le coach • merci à ceux qui gâtent le live 🎁', '🌹 THE TEAM JUST CASHED IN! if you loved it, a little rose or a like ❤️ keeps the coach going • thanks to everyone spoiling the live 🎁'],
    ['🆓 TOI AUSSI TU VEUX ENCAISSER AVEC LA TEAM ? crée ton compte démo GRATUIT et active ton coach • lien en bio • ce n\'est pas un conseil en investissement', '🆓 WANT TO CASH IN WITH THE TEAM TOO? open a FREE demo account and turn on your coach • link in bio • not financial advice'],
    ['🤖 ACTIVE TON COACH EN TEMPS RÉEL • il entre avec le bot, te suit jusqu\'au TP et t\'envoie toutes les news • gratuit • lien en bio 🎁', '🤖 TURN ON YOUR REAL-TIME COACH • it enters with the bot, follows you to TP and sends you all the news • free • link in bio 🎁'],
    ['⏸ PLUS ENVIE DE POSITIONS ? UN SEUL CLIC SUR « MON BOT » ET TU ARRÊTES • tu reprends quand tu veux • lien en bio', '⏸ NO MORE POSITIONS WANTED? ONE CLICK ON « MY BOT » AND YOU STOP • restart anytime • link in bio'],
    ['🆓 CRÉE TON COMPTE DÉMO ET TESTE GRATUITEMENT • zéro risque pour te faire la main 😉 • positions gratuites • lien en bio • ce n\'est pas un conseil en investissement (DYOR)', '🆓 OPEN A DEMO ACCOUNT AND TEST FOR FREE • zero risk to practise 😉 • free positions • link in bio • not financial advice (DYOR)'],
    ['🏦 ENVIE DE TRADER AVEC LE CAPITAL D\'UNE PROP FIRM ? codes promo Topstep / FundedNext dans le lien en bio 🎟 • commence par la démo 😉 • ce n\'est pas un conseil en investissement', '🏦 WANT TO TRADE WITH A PROP FIRM\'S CAPITAL? Topstep / FundedNext promo codes in the link in bio 🎟 • start with the demo 😉 • not financial advice'],
    ['risque de perte', 'risk of loss'],
    ['ATTENTION LA FEINTE sur', 'WATCH THE FAKE-OUT on'],
    ['le marché fait semblant de remonter… beaucoup vont acheter trop tôt et y laisser des plumes', 'the market is faking a bounce… many will buy too early and lose feathers'],
    ['le marché fait semblant de chuter… beaucoup vont vendre trop tôt et y laisser des plumes', 'the market is faking a drop… many will sell too early and lose feathers'],
    ['Ne te fais pas piéger', 'Don\'t get trapped'], ['ne cours pas après la bougie', 'don\'t chase the candle'],
    ['les gros adorent ce genre de piège', 'big players love this kind of trap'], ['qui va mordre à l\'hameçon ?', 'who\'s going to take the bait?'],
    ['Pfff… on s\'ennuie,', 'Ugh… so boring,'], ['est trop calme', 'is way too calm'], ['pense à tapoter l\'écran', 'remember to tap the screen'],
    ['et à t\'abonner', 'and follow'], ['Marché ennuyant sur', 'Boring market on'], ['allez, tapote l\'écran pour le réveiller', 'come on, tap the screen to wake it up'],
    ['et abonne-toi', 'and follow'],
    ['est tout calme… va te faire un café tranquille, on te prévient quand ça bouge', 'is super calm… go grab a coffee, we\'ll ping you when it moves'],
    ['Petit-déj time :', 'Breakfast time:'], ['se réveille doucement… le coach veille pour toi', 'is slowly waking up… the coach is watching for you'],
    ['fait la sieste… va manger un bout, le coach surveille pour toi', 'is napping… go grab a bite, the coach is watching for you'],
    ['Pause déj :', 'Lunch break:'], ['bouge pas d\'un poil… on te ping dès que ça part', 'isn\'t moving an inch… we\'ll ping you when it goes'],
    ['chill grave… prends une pause, le marché te fera signe', 'is chilling hard… take a break, the market will let you know'],
    ['Café de l\'aprèm ?', 'Afternoon coffee?'], ['est en mode tranquille… le coach reste connecté', 'is in chill mode… the coach stays connected'],
    ['est calme ce soir… va dîner, le coach garde un œil', 'is calm tonight… go have dinner, the coach keeps an eye on it'],
    ['Soirée chill :', 'Chill evening:'], ['ne fait rien de fou… on te prévient si ça s\'énerve', 'isn\'t doing anything crazy… we\'ll tell you if it heats up'],
    ['Il est tard et', 'It\'s late and'], ['dort à moitié… va te reposer, le coach veille', 'is half asleep… go get some rest, the coach is on watch'],
    ['roupille… recharge les batteries, le marché sera encore là demain', 'is snoozing… recharge your batteries, the market will still be here tomorrow'],
    ['sur ', 'on ']
  ].sort((a, b) => b[0].length - a[0].length);
  function enAnglais(t) { let x = String(t); for (const [fr, en] of EN) x = x.split(fr).join(en); return x; }
  const DUREE_MAIN = 15000, DUREE_MSG = 8000;

  // ───── style ─────
  const css = document.createElement('style');
  css.id = 'align-bande-css';
  css.textContent = `
  #align-bande{position:fixed;z-index:9999;height:86px;overflow:hidden;pointer-events:none;
    background:linear-gradient(90deg,#ff2d95,#8a2be2 50%,#1e90ff);border-radius:0 0 10px 10px;
    box-shadow:0 4px 14px rgba(0,0,0,.5);font:900 40px/86px system-ui,Segoe UI,Arial,sans-serif;color:#fff;
    text-shadow:0 2px 3px rgba(0,0,0,.45);transition:opacity .2s}
  #align-bande .piste{position:absolute;white-space:nowrap;will-change:transform}
  #align-bande .piste span{margin-right:70px}
  #align-bande .flash{position:absolute;inset:0;display:none;align-items:center;justify-content:flex-start;
    padding:0;white-space:nowrap;overflow:hidden;font:900 40px/86px system-ui,Segoe UI,Arial,sans-serif;
    background:linear-gradient(90deg,#ff4fa3,#ffd400);color:#000;text-shadow:none;text-transform:uppercase}   /* v7.4 : même rendu que la bande d'accueil (majuscules, 86 px, 40 px) */
  /* v5.4 : même taille d'écriture que la bande normale, une couleur par type d'info (plus de bande blanche) */
  #align-bande .flash.bulle{background:linear-gradient(90deg,#ff7ab8,#ffb3d6);color:#000}
  #align-bande .flash.tp{background:linear-gradient(90deg,#00c853,#ffd400);color:#000}
  #align-bande .flash.sl{background:linear-gradient(90deg,#ff1744,#ff8a65);color:#fff;text-shadow:0 2px 3px rgba(0,0,0,.45)}
  #align-bande .flash.membre{background:linear-gradient(90deg,#8a2be2,#ff2d95);color:#fff;text-shadow:0 2px 3px rgba(0,0,0,.45)}
  #align-bande .flash.proche{background:linear-gradient(90deg,#1e90ff,#00e5ff);color:#000}
  #align-bande .flash.bas{background:linear-gradient(90deg,#ff1744,#ff6d00);color:#fff;text-shadow:0 2px 3px rgba(0,0,0,.45)}
  #align-bande .flash.haut{background:linear-gradient(90deg,#00c853,#00e5ff);color:#000}
  #align-bande .flash.alerte{background:linear-gradient(90deg,#ff9100,#ffd400);color:#000}
  #align-bande .flash span{display:inline-block;will-change:transform}
  #align-bande.on .piste{visibility:hidden} #align-bande.on .flash{display:flex}
  [class*="common-tooltip__body"]{background:#ffc0dc!important;color:#000!important;max-width:330px!important;
    width:330px!important;font-weight:600!important;border:2px solid #ff4fa3!important;border-radius:10px!important}
  [class*="common-tooltip__body"] *{color:#000!important}`;
  document.head.appendChild(css);

  // ───── bande ─────
  const bande = document.createElement('div');
  bande.id = 'align-bande';
  bande.innerHTML = '<div class="piste"></div><div class="flash"></div>';
  document.body.appendChild(bande);
  const piste = bande.querySelector('.piste'), flash = bande.querySelector('.flash');
  // Voix optionnelle : une nouvelle page exige un clic explicite (politique audio du navigateur).
  // Une préférence « ON » persistée ne vaut pas autorisation de lecture après rechargement.
  let voixEtatInitial = false;
  try { localStorage.removeItem('alignVoixActive'); } catch (e) {}   // réinitialise un ancien ON qui ne peut pas déverrouiller l'audio
  const voixBtn = document.createElement('button');
  voixBtn.id = 'align-live-voice';
  voixBtn.type = 'button';
  voixBtn.textContent = voixEtatInitial ? '🔊 COACH VOCAL ON' : '🔇 COACH VOCAL OFF';
  voixBtn.setAttribute('aria-pressed', voixEtatInitial ? 'true' : 'false');
  voixBtn.title = 'Activer le commentateur vocal du live';
  voixBtn.style.cssText = 'position:fixed;left:18px;bottom:20px;z-index:10001;padding:11px 15px;border:2px solid #35d07f;border-radius:22px;background:linear-gradient(135deg,#123b2b,#10251f);color:#fff;font:800 13px system-ui;cursor:pointer;pointer-events:auto;box-shadow:0 0 18px rgba(53,208,127,.35)';
  document.body.appendChild(voixBtn);
  const voixLangueBtn = document.createElement('button');
  voixLangueBtn.type = 'button';
  let voixLangue = 'fr';
  try { voixLangue = localStorage.getItem('alignVoixLangue') === 'en' ? 'en' : 'fr'; } catch (e) {}
  voixLangueBtn.textContent = '🇫🇷 → 🇬🇧 Voix';
  voixLangueBtn.title = 'La voix parle en français puis en anglais';
  voixLangueBtn.style.cssText = 'position:fixed;right:18px;left:auto;bottom:20px;z-index:10001;padding:7px 10px;border:1px solid rgba(255,255,255,.55);border-radius:18px;background:rgba(18,18,28,.82);color:#fff;font:700 12px system-ui;cursor:pointer;pointer-events:auto';
  document.body.appendChild(voixLangueBtn);

  // Commande VISUELLE indépendante de la synthèse vocale : active/coupe les animations du live.
  let animationsActives = true;
  try { animationsActives = localStorage.getItem('alignAnimationsEnabled') !== '0'; } catch (e) {}
  const animationsBtn = document.createElement('button');
  animationsBtn.id = 'align-live-animations';
  animationsBtn.type = 'button';
  animationsBtn.setAttribute('aria-pressed', String(animationsActives));
  animationsBtn.title = 'Activer ou désactiver les animations visuelles ALIGN (sans modifier les voix)';
  animationsBtn.style.cssText = 'position:fixed;left:18px;bottom:72px;z-index:10002;padding:11px 15px;border:2px solid #ffd400;border-radius:22px;background:linear-gradient(135deg,#28200a,#171717);color:#fff;font:900 13px system-ui;cursor:pointer;pointer-events:auto;box-shadow:0 0 18px rgba(255,212,0,.28)';
  function appliquerAnimations() {
    // OFF masque uniquement le spectacle visuel. Les timers, flux, calculs,
    // commentaires, synthèse vocale et animations internes continuent en arrière-plan.
    document.documentElement.classList.toggle('align-animations-off', !animationsActives);
    animationsBtn.textContent = animationsActives ? '✨ ANIMATIONS ON' : '⏸ ANIMATIONS OFF';
    animationsBtn.setAttribute('aria-pressed', String(animationsActives));
  }
  document.body.appendChild(animationsBtn);
  animationsBtn.addEventListener('click', () => {
    animationsActives = !animationsActives;
    try { localStorage.setItem('alignAnimationsEnabled', animationsActives ? '1' : '0'); } catch (e) {}
    appliquerAnimations();
  });
  // Dock unique des commandes ALIGN : toujours en bas, repliable, sans recouvrir l'en-tête TradingView.
  document.getElementById('align-live-controls-dock')?.remove();
  const controlsDock = document.createElement('div');
  controlsDock.id = 'align-live-controls-dock';
  controlsDock.setAttribute('role', 'group');
  controlsDock.setAttribute('aria-label', 'Commandes ALIGN');
  controlsDock.style.cssText = 'position:fixed!important;left:16px!important;right:auto!important;top:auto!important;bottom:16px!important;z-index:2147483000!important;display:flex!important;align-items:flex-end!important;justify-content:flex-start!important;gap:8px!important;max-width:calc(100vw - 32px)!important;pointer-events:auto!important;';
  const controlsDockItems = document.createElement('div');
  controlsDockItems.id = 'align-live-controls-items';
  controlsDockItems.style.cssText = 'display:flex;align-items:center;justify-content:flex-start;flex-wrap:wrap;gap:8px;max-width:calc(100vw - 90px);pointer-events:auto;';
  [voixBtn, voixLangueBtn, animationsBtn].forEach(button => {
    button.style.setProperty('position', 'relative', 'important');
    button.style.setProperty('left', 'auto', 'important');
    button.style.setProperty('right', 'auto', 'important');
    button.style.setProperty('top', 'auto', 'important');
    button.style.setProperty('bottom', 'auto', 'important');
    button.style.setProperty('z-index', 'auto', 'important');
    button.style.setProperty('margin', '0', 'important');
    controlsDockItems.appendChild(button);
  });
  const controlsDockToggle = document.createElement('button');
  controlsDockToggle.id = 'align-live-controls-toggle';
  controlsDockToggle.type = 'button';
  controlsDockToggle.style.cssText = 'position:relative!important;min-width:42px;padding:9px 12px;border:1px solid rgba(255,255,255,.55);border-radius:18px;background:#18212b;color:#fff;font:800 13px system-ui;cursor:pointer;pointer-events:auto;box-shadow:0 2px 12px rgba(0,0,0,.35);';
  let controlsDockCollapsed = false;
  try { controlsDockCollapsed = localStorage.getItem('alignControlsDockCollapsed') === '1'; } catch (e) {}
  function appliquerDockCommandes() {
    controlsDockItems.style.display = controlsDockCollapsed ? 'none' : 'flex';
    controlsDockToggle.textContent = controlsDockCollapsed ? 'ALIGN +' : '−';
    controlsDockToggle.title = controlsDockCollapsed ? 'Afficher les commandes ALIGN' : 'Réduire les commandes ALIGN';
    controlsDockToggle.setAttribute('aria-expanded', String(!controlsDockCollapsed));
  }
  controlsDockToggle.addEventListener('click', () => {
    controlsDockCollapsed = !controlsDockCollapsed;
    try { localStorage.setItem('alignControlsDockCollapsed', controlsDockCollapsed ? '1' : '0'); } catch (e) {}
    appliquerDockCommandes();
  });
  controlsDock.append(controlsDockItems, controlsDockToggle);
  document.body.appendChild(controlsDock);
  appliquerDockCommandes();
  const cssAnimationsToggle = document.createElement('style');
  cssAnimationsToggle.textContent = 'html.align-animations-off #align-bande,html.align-animations-off #align-pnl,html.align-animations-off .align-punch,html.align-animations-off .align-ping,html.align-animations-off .align-coeur,html.align-animations-off .align-billet,html.align-animations-off .align-argent,html.align-animations-off #align-feu,html.align-animations-off #align-flash-or,html.align-animations-off #align-show,html.align-animations-off #align-cadre,html.align-animations-off #align-ennui,html.align-animations-off #align-chrono,html.align-animations-off #align-etiq,html.align-animations-off #align-masque{visibility:hidden!important;opacity:0!important;pointer-events:none!important}';
  document.head.appendChild(cssAnimationsToggle);
  appliquerAnimations();
  voixLangueBtn.addEventListener('click', () => {
    voixLangue = 'fr';   // v12.2.7 (règle d'Adel) : toujours français PUIS anglais, la langue n'est plus à choisir
    voixLangueBtn.textContent = '🇫🇷 → 🇬🇧 Voix';
    try { localStorage.setItem('alignVoixLangue', voixLangue); } catch (e) {}
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (e) {}
  });
  let voixActive = voixEtatInitial, voixDerniere = 0, voixTexte = '', voixDerniereFR = 0, voixTexteEN = '';
  let dernierCommentaireIA = null;  // dernier commentaire réellement affiché, pas un texte d'accueil
  // v12.2.7 : voix la plus humaine disponible (gratuite, intégrée au navigateur / à Windows)
  const VOIX_NATURELLES = /natural|neural|online|premium|enhanced|google|denise|vivienne|henri|eloise|remy|amélie|amelie|hortense|audrey|julie|charlotte|pierre|paul|thomas|jenny|aria|guy|samantha|ava|david|mark|hazel|zira/i;
  let voixEnAttente = null;  // commentaire FR gardé si les voix du navigateur arrivent après le premier message
  function rafraichirVoix() { try { return window.speechSynthesis.getVoices() || []; } catch (e) { return []; } }
  function voixSurVoixChangees() {
    rafraichirVoix();
    const attente = voixEnAttente; voixEnAttente = null;
    if (voixActive && attente) parlerLive(attente, true);
  }
  if ('speechSynthesis' in window) {
    try { window.speechSynthesis.addEventListener('voiceschanged', voixSurVoixChangees); } catch (e) {}
  }
  function choisirVoix(lang) {
    try {
      const toutes = window.speechSynthesis.getVoices() || [];
      const dansLangue = toutes.filter(v => String(v.lang || '').toLowerCase().startsWith(lang));
      // v12.2.8 (demande d'Adel) : UNIQUEMENT une voix naturelle. Plus de repli sur la voix robot.
      return dansLangue.find(v => VOIX_NATURELLES.test(v.name)) || null;
    } catch (e) { return null; }
  }
  voixBtn.addEventListener('click', () => {
    if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
      voixBtn.textContent = '⚠️ Voix indisponible'; return;
    }
    voixActive = !voixActive;
    try { localStorage.setItem('alignVoixActive', voixActive ? '1' : '0'); } catch (e) {}
    if (voixActive) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.resume();
      voixBtn.textContent = '🔊 COACH VOCAL ON';
      voixBtn.setAttribute('aria-pressed', 'true');
      // Pas de phrase d'accueil : relire uniquement le dernier commentaire IA déjà affiché,
      // et seulement s'il correspond toujours au marché actuellement observé.
      voixDerniere = Date.now();
      const dernier = dernierCommentaireIA;
      if (dernier && (!dernier.market || dernier.market === codeMarche())) parlerLive(dernier, true);
    } else {
      try { window.speechSynthesis.cancel(); } catch (e) {}   // v12.2.8 : OFF coupe tout ce qui est en file
      voixEnAttente = null;
      signalVoix('STOP', 'fr');
      voixBtn.textContent = '🔇 COACH VOCAL OFF';
      voixBtn.setAttribute('aria-pressed', 'false');
    }
  });
  let voixUtterance = null;   // v12.2.10 : référence vivante de la phrase en cours (anti ramasse-miettes)
  // v12.2.13 : signal minimal de synchronisation voix vers ALIGN LIVE (aucun texte vocal transmis).
  function signalVoix(action, lang) {
    const message = 'ALIGN_VOICE|' + action + '|' + (lang || 'fr') + '|' + Date.now();
    const url = 'https://ntfy.sh/' + SUJET + '-voix';
    try {
      if (typeof GM_xmlhttpRequest === 'function') {
        GM_xmlhttpRequest({ method: 'POST', url, data: message, timeout: 5000, onerror: () => {}, ontimeout: () => {} });
      } else {
        fetch(url, { method: 'POST', body: message, keepalive: true }).catch(() => {});
      }
    } catch (e) {}
  }
  function parlerLive(item, forcer = false) {
    if (!voixActive || !item || (item.source !== 'ia' && item.source !== 'marche') ||!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) return 0;
    // v12.2.7 (règle d'Adel) : chaque info est dite en FRANÇAIS, puis la même en ANGLAIS, jamais mélangées.
    const anglais = !!item.en;
    if (anglais && item.source === 'marche' && !item.anglaisTraduit) return 0;  // une bulle non traduite reste silencieuse en EN
    const maintenant = Date.now();
    const suiteAnglaise = anglais && maintenant - voixDerniereFR < 60000;   // l'anglais suit le français qu'on vient de dire
    if (anglais && !suiteAnglaise && !forcer) return 0;                     // pas d'anglais orphelin, sauf relecture explicite
    if (!anglais && maintenant - voixDerniere < 12000 && !forcer) return 0; // pas de mitraillette vocale
    let phrase = String(item.texte || '').replace(/^🇫🇷\s*|^🇬🇧\s*/, '')
      .replace(/⚠️ Ceci n'est pas un conseil en investissement[^•]*/gi, '')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/[\p{Extended_Pictographic}\uFE0F]/gu, ' ')
      .replace(/\s+/g, ' ').trim();
    // v12.2.6 : on retire SEULEMENT les morceaux « disclaimer » et « appel au public » (séparés par •),
    // jamais le commentaire de marché lui-même ; s'il ne reste rien de réel, on ne dit rien.
    const NON_MARCHE = /lien (en|dans la) bio|link in (the )?bio|spectacle|tapote|tap the screen|tap on the screen|partage|share (the|this) (live|stream|video)|share it|DYOR|do your own research|fais tes propres recherches|conseil en investissement|financial advice|investment advice|risque (élevé |eleve )?de perte|high risk of (capital )?loss|risk of loss|\brisques?\b|\brisks?\b|perte en capital|capital loss/i;
    phrase = phrase.split(/\s*•\s*/).filter(m => m && !NON_MARCHE.test(m)).join(' • ').trim();
    if (phrase.length < 12 || (!forcer && phrase === (anglais ? voixTexteEN : voixTexte))) return 0;
    // v12.2.6 : jamais de phrase coupée au milieu : on ne lit qu'une phrase complète
    if (phrase.length > 220) {
      const coupe = phrase.slice(0, 220).match(/^.*[.!?…]/);
      if (!coupe) return 0;
      phrase = coupe[0];
    }
    try {
      const utterance = new SpeechSynthesisUtterance(phrase);
      utterance.lang = anglais ? 'en-US' : 'fr-FR';
      const v = choisirVoix(anglais ? 'en' : 'fr');
      if (!v) {
        // Les voix sont souvent chargées après document-idle : retenter le commentaire FR quand voiceschanged arrive.
        if (!anglais && voixActive) voixEnAttente = item;
        return 0;   // aucune voix naturelle disponible : silence plutôt qu'une voix robot
      }
      utterance.voice = v;
      utterance.rate = 1.04;     // ton d'animateur : un peu plus vif
      utterance.pitch = 1.08;
      if (!anglais) window.speechSynthesis.cancel();   // l'anglais se met à la suite du français, sans le couper
      // v12.2.10 : Chrome coupe la lecture (2-3 mots) si l'objet utterance est ramassé par le ramasse-miettes :
      // on garde une référence jusqu'à la fin de la phrase.
      voixUtterance = utterance;
      utterance.onstart = () => signalVoix('START', anglais ? 'en' : 'fr');
      utterance.onend = utterance.onerror = () => { signalVoix('STOP', anglais ? 'en' : 'fr'); if (voixUtterance === utterance) voixUtterance = null; };
      window.speechSynthesis.speak(utterance);
      if (anglais) { voixTexteEN = phrase; voixDerniereFR = 0; }
      else { voixTexte = phrase; voixDerniereFR = maintenant; }
      voixDerniere = maintenant;
      return Math.max(4000, Math.ceil(phrase.length * 75 + 500));
    } catch (e) { return 0; }
  }
  let extra = [];
  // v4.8 : la bande dit toujours ce qu'on regarde (marché + unité), mise à jour dès que la vue change
  function vueTxt() {
    // TradingView peut exposer activeChart() avant que son modèle interne soit prêt.
    // La lecture du symbole / timeframe ne doit jamais interrompre le démarrage de la bande.
    try {
      const c = chart();
      if (!c || typeof c.symbol !== 'function' || typeof c.resolution !== 'function') return '';
      const s = String(c.symbol() || ''), r = String(c.resolution() || '');
      if (!s || !r) return '';
      const m = /BTC/i.test(s) ? '🟠 BTC' : /XAU|GOLD/i.test(s) ? '🥇 GOLD' : s.split(':').pop();
      const u = /^\d+$/.test(r) ? (+r >= 60 ? (+r / 60) + 'H' : r + ' MIN') : r === 'D' || r === '1D' ? '1 JOUR' : r;
      return '📺 VUE : ' + m + ' • ' + u;
    } catch (e) {
      return '';
    }
  }
  let vueVue = '';
  setInterval(() => { const v = vueTxt(); if (v !== vueVue) { vueVue = v; remplir(); } }, 2000);
  // v6.7 : TikTok ≠ YouTube. TikTok = « tapote l'écran », « lien en bio » ; YouTube = « like 👍 », « active la cloche 🔔 »,
  // « lien en description ». Réglage gardé dans le navigateur ; « les deux » = un texte qui marche partout (un seul écran filmé).
  let PLATEFORME = 'tiktok';
  try { PLATEFORME = localStorage.getItem('alignPlateforme') || 'tiktok'; } catch (e) {}
  function plateforme(t) {
    t = String(t);
    if (PLATEFORME === 'youtube') return t
      .replace(/TAPOTE L'ÉCRAN/g, 'LIKE 👍 • ACTIVE LA CLOCHE 🔔').replace(/tapote(r)? (sur )?l'écran/gi, 'mettre un like 👍')
      .replace(/TAP THE SCREEN/g, 'LIKE 👍 • TURN ON THE BELL 🔔').replace(/tap the screen/gi, 'hit like 👍')
      .replace(/LIEN EN BIO/g, 'LIEN EN DESCRIPTION').replace(/lien en bio/gi, 'lien en description')
      .replace(/LINK IN BIO/g, 'LINK IN DESCRIPTION').replace(/link in bio/gi, 'link in description');
    if (PLATEFORME === 'les2') return t
      .replace(/TAPOTE L'ÉCRAN/g, 'TAPOTE / LIKE 👍').replace(/tapote(r)? (sur )?l'écran/gi, 'tapoter / liker 👍')
      .replace(/TAP THE SCREEN/g, 'TAP / LIKE 👍').replace(/tap the screen/gi, 'tap / like 👍')
      .replace(/LIEN EN BIO/g, 'LIEN EN BIO / DESCRIPTION').replace(/lien en bio/gi, 'lien en bio / description')
      .replace(/LINK IN BIO/g, 'LINK IN BIO / DESCRIPTION').replace(/link in bio/gi, 'link in bio / description');
    return t;
  }
  function remplir() {
    const v = vueTxt();
    const iEN = BASE.indexOf('👉 FOLLOW • SHARE • TAP THE SCREEN');   // v7.8 : on repère les phrases anglaises de la bande d'accueil
    const items = (v ? [[v, 0]] : []).concat(BASE.map((t, i) => [t, iEN >= 0 && i >= iEN]), extra.slice(-3).map(t => [t, 0]));
    const html = items.map(([t, en]) => '<span' + (en ? ' class="en"' : '') + '>' + esc(plateforme(t)) + '</span>').join('');
    piste.innerHTML = html + html;
  }
  function esc(s) { return String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
  remplir();

  function zoneGraphique() {
    const c = document.querySelector('.chart-markup-table') || document.querySelector('.chart-container');
    return c ? c.getBoundingClientRect() : { left: 0, top: 0, width: innerWidth };
  }
  let x = 0, last = performance.now(), raf;
  function anim(now) {
    const r = zoneGraphique();
    const axe = 0;     // v7.6 (demande d'Adel) : la bande couvre aussi l'échelle de prix en haut (plus propre)
    const marge = 40;  // à gauche : un peu plus large (v5.2) tout en restant dans la zone filmée par TikTok
    bande.style.left = (r.left + marge) + 'px';
    bande.style.top = r.top + 'px';
    bande.style.width = Math.max(200, r.width - axe - marge) + 'px';
    const dt = Math.min(64, now - last); last = now;
    x -= dt * 0.09;
    const demi = piste.scrollWidth / 2;
    if (demi > 0 && -x >= demi) x += demi;
    piste.style.transform = 'translateX(' + x + 'px)';
    // v7.9 (demande d'Adel : « je n'arrive pas à fermer la fenêtre à cause de la bande ») : toutes les 0,4 s,
    // si une fenêtre / un menu TradingView est ouvert, la bande et les pastilles se cachent ; la pub « Go Pro » est fermée toute seule
    if (now - (anim.vu || 0) > 400) { anim.vu = now; try {
      const pub = document.querySelector('[data-dialog-name="gopro"] button[aria-label="Fermeture"]'); if (pub) pub.click();
      // Ne masquer le spectacle que lorsqu'un vrai dialogue/menu est visible à l'écran.
      // TradingView conserve des conteneurs [data-dialog-name] cachés dans le DOM : leur simple présence ne doit jamais couper le live.
      const overlayVisible = el => {
        if (!el || !el.isConnected || el.closest('[aria-hidden="true"]')) return false;
        const st = getComputedStyle(el), r = el.getBoundingClientRect();
        return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity || 1) > 0.01
          && r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
      };
      const overlayOuvert = Array.from(document.querySelectorAll('[role="dialog"], [data-dialog-name], [data-name="menu-inner"]')).some(overlayVisible);
      document.documentElement.classList.toggle('align-cache', overlayOuvert);
    } catch (e) {} }
    raf = requestAnimationFrame(anim);
  }
  raf = requestAnimationFrame(anim);

  // ───── messages (dans la bande, plus de fenêtre au centre) ─────
  const file = []; let occupe = false;
  // v5.1 : chaque info du bot (TP, SL, entrée, zone, pulsion…) passe 2 fois de suite dans la bande puis disparaît
  // (plus rien n'est ajouté pour toujours à la bande qui défile)
  // v5.4 : une couleur par type, et les infos importantes (TP, SL, entrée, nouvel abonné, prépare-toi) passent DEVANT la file
  function genre(t) {
    if (/TP\d? TOUCH|OBJECTIF FINAL|BRAVO/i.test(t)) return 'tp';
    if (/stop touch|SL TOUCH/i.test(t)) return 'sl';
    if (/REJOINT LA TEAM|BIENVENUE|nouvel abonn/i.test(t)) return 'membre';
    if (/FRÔLÉ|FROLE|DIRECTION TP|approche du TP|vers le TP/i.test(t)) return 'proche';
    if (/prépare-toi|ENTRE EN POSITION|POSITION ALIGN CONFIRMÉE|zone clé|pas de panique|revient vers l'entrée|NEWS/i.test(t)) return 'alerte';
    return '';
  }
  // v6.3 (règle d'Adel) : AUCUN chiffre de prix sur la bande — on intrigue, le détail est dans le lien en bio
  // v6.3 : ni prix, ni ENTRÉE / SL / TP / stop sur la bande (risque TikTok + on garde le détail pour le lien en bio)
  // v9.1 (règle d'Adel) : la bande donne une INFO, jamais un SENS : aucune flèche ni « ça va monter / baisser »
  function sansPrix(t) { return String(t)
    .replace(/[↑↓⬆⬇▲▼△▽↗↘↖↙⤴⤵🔼🔽📈📉]\uFE0F?/gu, '').replace(/\b(va|vont|devrait|devraient)\s+(monter|baisser|descendre|chuter|grimper|remonter|rebondir)\b/gi, '$1 se décider').replace(/\b(will|should)\s+(go up|go down|rise|fall|drop|bounce)\b/gi, '$1 decide')
    .replace(/ENTRE EN POSITION/gi, 'PASSE À L\'ACTION').replace(/SL (à|a) l['’]entrée/gi, 'risque zéro').replace(/l['’]entrée/gi, 'la zone').replace(/\bTP\s?\d?\b/g, 'objectif').replace(/\bSL\b|\bstop\b/gi, 'protection')
    .replace(/\bENTRÉE\b|\bentrée\b/g, 'zone').replace(/\(ligne (bleue|rouge|jaune)\)/gi, '').replace(/\d{1,3}(?:[\s\u202f\u00a0]\d{3})+(?:[.,]\d+)?|\d{3,}(?:[.,]\d+)?/g, '').replace(/\(\s*\)|:\s*(?=•)/g, '').replace(/\btelegram\b/gi, ' ').replace(/\s{2,}/g, ' ').trim(); }
  function montrer(texte, bulle, fois, couleur, devant, source) {
    const g = couleur || genre(texte);
    texte = sansPrix(texte);
    const urgent = g && g !== 'proche' ? 1 : 0;
    // v6.4 : chaque info passe en français PUIS en anglais (au moins 2 passages)
    // v12.2.8 : plus de « risque de perte » ajouté à chaque info : la mention légale reste seulement dans le pied de bande
    // v7.3 (règle d'Adel, 15/11) : chaque info passe 2 fois en français PUIS 2 fois en anglais
    const traductionEN = enAnglais(texte), anglaisTraduit = traductionEN !== texte;
    const nPass = Math.max(4, 2 * (fois || 1)), items = []; for (let i = 0; i < nPass; i++) items.push({ texte: (i >= nPass / 2 ? '🇬🇧 ' : '🇫🇷 ') + plateforme(i >= nPass / 2 ? traductionEN : texte), bulle, g, en: i >= nPass / 2, anglaisTraduit, source: source || 'live', market: source === 'ia' ? codeMarche() : '' });   // v12.2.12 : garde la preuve de traduction pour ne pas vocaliser du français avec une voix EN
    if (devant) { file.splice(0, file.length, ...items, ...file.filter(m => m.g && m.g !== 'proche')); couper(); }   // v7.5 : clic sur une zone = la bande en parle TOUT DE SUITE
    else if (urgent) { let k = 0; while (k < file.length && file[k].g && file[k].g !== 'proche') k++; file.splice(k, 0, ...items); }
    else file.push(...items);
    suivant();
  }
  let animCur = null, timerCur = null;
  function couper() { if (!occupe) return; try { animCur && animCur.cancel(); } catch (e) {} clearTimeout(timerCur); bande.classList.remove('on'); occupe = false; }
  function suivant() {
    if (occupe || !file.length) return;
    occupe = true;
    const m = file.shift();
    if (m.source === 'ia') dernierCommentaireIA = m;
    flash.innerHTML = '<span>' + esc(m.texte) + '</span>';   // le message défile vite (lisible sur téléphone, même si TikTok coupe les bords)
    flash.className = 'flash' + (m.g ? ' ' + m.g : m.bulle ? ' bulle' : '') + (m.en ? ' en' : '');
    bande.classList.add('on');
    const voixDuree = parlerLive(m); // seule la narration IA est prononcée ; la durée visuelle suit sa lecture
    const sp = flash.firstChild, W = bande.clientWidth, w = sp.offsetWidth;
    const dur = Math.max(4000, (W + w) / 0.38, voixDuree);      // v5.4 : plus rapide (info en temps réel), toujours lisible
    animCur = sp.animate([{ transform: 'translateX(' + W + 'px)' }, { transform: 'translateX(' + (-w) + 'px)' }], { duration: dur, easing: 'linear' });
    timerCur = setTimeout(() => { bande.classList.remove('on'); occupe = false; if (!file.length) x = 0; suivant(); }, dur);   // v7.4 : après les infos, la bande d'accueil repart du DÉBUT (en français)
  }

  // v5.3 : de temps en temps une astuce (2 passages) pour apprendre à lire le graphique, sans aucun prix ni sens
  // (les prix diffèrent d'un broker à l'autre : on montre OÙ regarder, la suite est « lien en bio »)
  const ASTUCES = [
    "👀 Astuce : mets-toi en vue 15 min et repère le dernier plus haut • c'est souvent là que le prix réagit • les infos en temps réel : lien en bio 🎁",
    "📉 Astuce : en vue 15 min, repère le dernier plus bas • s'il casse en CLÔTURE, le mouvement peut continuer • lien en bio 🎁",
    "🎯 Astuce : l'étiquette ENTRÉE = la zone que le coach surveille • on attend la clôture 15 min • lien en bio 🎁",
    "🕯 Astuce : une mèche seule ne suffit pas • c'est la CLÔTURE de la bougie 15 min qui décide • lien en bio 🎁",
    "🔵 Astuce : ligne bleue = TP • ligne rouge = SL • le coach te dit quand ça s'approche • lien en bio 🎁",
    "🔎 Pour l'analyse complète de BTC et GOLD, ouvre le lien dans la bio • le LIVE continue ici 🎙"
  ];
  EN.push(["Pour l'analyse complète de BTC et GOLD, ouvre le lien dans la bio", "For the full BTC and GOLD analysis, open the link in the bio"],
          ["Tu veux savoir si le feu vert est confirmé ? Ouvre le lien dans la bio pour voir le plan complet.", "Want to know if the green light is confirmed? Open the link in the bio to see the full plan."]);
  // v8.5 (demande d'Adel) : phrases inventées par l'IA gratuite du bot (FR | EN), toujours nouvelles, jamais de prix
  const HAUT_TABLEAU = 3.4;   // hauteur du tableau des unités ≈ 3,4 × la ligne du bas
  // v8.5 (constat d'Adel) : la bande ne dit « ça encaisse / vous êtes rentrés ? » QUE si le bot a vraiment donné la position (Telegram)
  const botPos = {};
  function cleMarche(t) { const x = String(t || '').match(/BTC|GOLD|XAU/i); return x ? x[0].toUpperCase().replace('XAU', 'GOLD') : ''; }
  function botSuivi(t) {
    const k = cleMarche(t); if (!k) return;
    if (/ENTRE EN POSITION|POSITION ALIGN CONFIRMÉE/i.test(t)) botPos[k] = Date.now();
    else if (/TP2 TOUCH|OBJECTIF FINAL|SL TOUCH|STOP TOUCH|POSITION (FERMÉE|CLÔTURÉE)/i.test(t)) delete botPos[k];
  }
  // Le flux ntfy annonce les nouvelles entrées, mais un live ouvert après le bot peut manquer l'événement.
  // Le JSON public expose seulement l'état (entree/preparation), jamais la direction ni les niveaux.
  const BOT_STATE_URL = 'https://raw.githubusercontent.com/adelkhatra-bit/trading-align-/live-data/live.json';
    let botEtatSyncT = null;
  // v12.2.8 : état officiel du bot par marché (calme / preparation / entree). Sans état confirmé, la bande ne promet rien.
  const botEtat = {};
  function botAConfirme() { const k = codeMarche(); return !!k && (botEtat[k] === 'preparation' || botEtat[k] === 'entree'); }
  async function synchroniserEtatBot() {
    try {
      const rep = await fetch(BOT_STATE_URL + '?t=' + Date.now(), { cache: 'no-store' });
      if (!rep.ok) return;
      const data = await rep.json();
      const maj = Number(data && data.maj || 0) * 1000;
      if (!maj || Date.now() - maj > 10 * 60 * 1000 || maj > Date.now() + 60000) { for (const k in botEtat) delete botEtat[k]; return; }
      for (const item of (Array.isArray(data.marches) ? data.marches : [])) {
        const k = cleMarche(item && item.m);
        if (!k) continue;
        botEtat[k] = item.etat;
        if (item.etat === 'entree') {
          const dejaAnnonce = !!botPos[k] && Date.now() - botPos[k] < 12 * 3600 * 1000;
          botPos[k] = Date.now();
          // Si la page LIVE a raté l'événement ntfy d'entrée ou s'ouvre après le bot,
          // elle annonce l'état réellement ouvert une seule fois et relance le coach d'ambiance.
          if (!dejaAnnonce) montrer('🎯 POSITION ALIGN ACTIVE SUR ' + k + ' • le coach suit le trade avec la team • lien en bio', true, 1, 'proche', false);
        } else {
          delete botPos[k];
        }
      }
    } catch (e) {}
  }
  synchroniserEtatBot();
  botEtatSyncT = setInterval(synchroniserEtatBot, 15000);
  EN.push([' a touché l\'objectif du graphique • pas de position du coach cette fois ⏳ • attends le prochain cycle : lien en bio', ' touched the chart target • no coach trade this time ⏳ • wait for the next cycle: link in bio']);
  function botDedans(m) { const t = botPos[cleMarche(m)]; return !!t && Date.now() - t < 12 * 3600 * 1000; }
  // v8.6 : l'animateur du live (trader pro qui connaît le marché par cœur) — jamais de prix
  const COACH = { anim: ["🎙 {m} respire… et moi je sais déjà où il va 😏 • 50 taps et je lâche un indice 👆", "🤔 {m} fait le calme avant la tempête… TOI tu dis quoi : ça monte ou ça descend ? écris-le 👇", "😤 {m} attend que VOUS tapiez… personne tape = je garde l'info pour moi 🤫", "👀 {m} : les gros joueurs se placent en silence… toi t'es prêt ou tu dors ? 👆 tapote si t'es là", "🧠 {m} : un vrai trader n'attend pas le mouvement, il l'ANTICIPE • tu veux savoir comment ? lien en bio 😏", "🔥 {m} : je compte jusqu'à cent taps et je vous dis ce que je vois 👀 • allez la team !", "💬 {m} : écris « LONG » ou « SHORT » en commentaire… on verra qui avait raison 😎", "⏳ {m} : le marché s'endort, mais moi non 😏 • partage le live, quand ça part tu me remercieras", "🎯 {m} : je connais ce marché par cœur… et là il prépare un coup 👀 • t'es dedans ou tu regardes ? 👇", "🙋 {m} : tu viens d'arriver ? bienvenue 👋 regarde d'abord le spectacle, ne rentre pas tout de suite • partage le live 🙏 • lien en bio",
    // v10.1 (demande d'Adel) : on remet gentiment à leur place les petits malins, toujours avec le sourire
    "😝 {m} : y'en a qui rentrent sans attendre le feu vert… et après ils pleurent dans les commentaires 😭 • ici on attend le ✅, on est disciplinés 😎",
    "🚦 {m} : pas de feu vert = pas d'entrée • les petits malins qui rentrent avant, on se retrouve dans les commentaires… pour les mouchoirs 🤧😝",
    "😎 {m} : au lieu de dire des bêtises en commentaire, tapote et partage 👆 • ou va voir un live d'amateurs, nous on est disciplinés 😉",
    "🧘 {m} : la patience paie, la précipitation coûte • les pros attendent le signal, les autres attendent un miracle 😝",
    "😝 {m} : c'est pas parce que je dis « prépare-toi » que je t'ai dit d'y aller… reste concentré, attends le feu vert 🚦",
    "🍿 {m} : le marché fait la sieste… perso je me mets un petit film, repasse dans une heure 😝 • les fans, tapotez MDR 👆",
    "😴 {m} coincé dans sa zone… va boire un café, le coach te prévient quand ça se réveille ☕ • connecte-toi : lien en bio",
    "⏰ {m} : les vrais mouvements arrivent aux ouvertures (Londres, New York)… d'ici là, tapote MDR si t'es encore là 😂",
    "🤫 {m} : chez ALIGN on ne devine pas, on CONFIRME • tu veux le feu vert en temps réel ? active ton coach, lien en bio 🎁"],
    rebond: ["📉 {m} est en bas de sa zone… tu penses qu'il va REBONDIR ou CASSER ? dis-le en commentaire 👇", "🤔 {m} touche le plancher… rebond ou chute ? 👆 tapote si tu crois au rebond"],
    cassure: ["📈 {m} est en haut de sa zone… CASSURE ou REJET ? écris ton pronostic 👇", "😏 {m} tape le plafond… ça passe ou ça repart en bas ? 👆 tapote si tu dis que ça passe"] };
  EN.push([" respire… et moi je sais déjà où il va 😏 • 50 taps et je lâche un indice 👆", " breathes… and I already know where it's going 😏 • 50 taps and I drop a hint 👆"], [" fait le calme avant la tempête… TOI tu dis quoi : ça monte ou ça descend ? écris-le 👇", " is the calm before the storm… YOU tell me: up or down? write it 👇"], [" attend que VOUS tapiez… personne tape = je garde l'info pour moi 🤫", " is waiting for YOU to tap… nobody taps = I keep the info to myself 🤫"], [" : les gros joueurs se placent en silence… toi t'es prêt ou tu dors ? 👆 tapote si t'es là", " : big players are positioning quietly… are you ready or sleeping? 👆 tap if you are here"], [" : un vrai trader n'attend pas le mouvement, il l'ANTICIPE • tu veux savoir comment ? lien en bio 😏", " : a real trader doesn't wait for the move, he ANTICIPATES it • want to know how? link in bio 😏"], [" : je compte jusqu'à cent taps et je vous dis ce que je vois 👀 • allez la team !", " I count to a hundred taps and I tell you what I see 👀 • come on team!"], [" : écris « LONG » ou « SHORT » en commentaire… on verra qui avait raison 😎", " write « LONG » or « SHORT » in the comments… we'll see who was right 😎"], [" : le marché s'endort, mais moi non 😏 • partage le live, quand ça part tu me remercieras", " the market falls asleep, but I don't 😏 • share the live, when it moves you'll thank me"], [" : je connais ce marché par cœur… et là il prépare un coup 👀 • t'es dedans ou tu regardes ? 👇", " I know this market by heart… and it's preparing a move 👀 • are you in or just watching? 👇"], [" : tu viens d'arriver ? bienvenue 👋 regarde d'abord le spectacle, ne rentre pas tout de suite • partage le live 🙏 • lien en bio", " just arrived? welcome 👋 watch the show first, don't jump in right away • share the live 🙏 • link in bio"], [" est en bas de sa zone… tu penses qu'il va REBONDIR ou CASSER ? dis-le en commentaire 👇", " is at the bottom of its range… do you think it will BOUNCE or BREAK? tell us in the comments 👇"], [" touche le plancher… rebond ou chute ? 👆 tapote si tu crois au rebond", " touches the floor… bounce or drop? 👆 tap if you believe in the bounce"], [" est en haut de sa zone… CASSURE ou REJET ? écris ton pronostic 👇", " is at the top of its range… BREAKOUT or REJECTION? write your call 👇"], [" tape le plafond… ça passe ou ça repart en bas ? 👆 tapote si tu dis que ça passe", " hits the ceiling… does it break or drop back? 👆 tap if you say it breaks"]);
  EN.push([" : y'en a qui rentrent sans attendre le feu vert… et après ils pleurent dans les commentaires 😭 • ici on attend le ✅, on est disciplinés 😎", ": some jump in without the green light… then cry in the comments 😭 • here we wait for the ✅, we're disciplined 😎"],
    [" : pas de feu vert = pas d'entrée • les petits malins qui rentrent avant, on se retrouve dans les commentaires… pour les mouchoirs 🤧😝", ": no green light = no entry • smart guys who jump in early, see you in the comments… with tissues 🤧😝"],
    [" : au lieu de dire des bêtises en commentaire, tapote et partage 👆 • ou va voir un live d'amateurs, nous on est disciplinés 😉", ": instead of talking nonsense in the comments, tap and share 👆 • or go watch an amateur live, we're disciplined 😉"],
    [" : la patience paie, la précipitation coûte • les pros attendent le signal, les autres attendent un miracle 😝", ": patience pays, rushing costs • pros wait for the signal, others wait for a miracle 😝"],
    [" : c'est pas parce que je dis « prépare-toi » que je t'ai dit d'y aller… reste concentré, attends le feu vert 🚦", ": just because I say « get ready » doesn't mean I said go… stay focused, wait for the green light 🚦"],
    [" : le marché fait la sieste… perso je me mets un petit film, repasse dans une heure 😝 • les fans, tapotez MDR 👆", ": the market is napping… I'm putting a movie on, come back in an hour 😝 • fans, tap LOL 👆"],
    [" coincé dans sa zone… va boire un café, le coach te prévient quand ça se réveille ☕ • connecte-toi : lien en bio", " stuck in its range… go grab a coffee, the coach warns you when it wakes up ☕ • connect: link in bio"],
    [" : les vrais mouvements arrivent aux ouvertures (Londres, New York)… d'ici là, tapote MDR si t'es encore là 😂", ": real moves come at the opens (London, New York)… until then, tap LOL if you're still here 😂"],
    [" : chez ALIGN on ne devine pas, on CONFIRME • tu veux le feu vert en temps réel ? active ton coach, lien en bio 🎁", ": at ALIGN we don't guess, we CONFIRM • want the green light in real time? turn on your coach, link in bio 🎁"]);   // v10.1
  const PREVENU = ' • tu as vu le chrono ? pourquoi t\'es pas encore inscrit ? 👉 viens dans le lien en bio';
  EN.push(['😏 JE T\'AVAIS PRÉVENU ! ', '😏 I TOLD YOU SO! '], [PREVENU, ' • did you see the timer? why aren\'t you signed up yet? 👉 come to the link in bio']);
  // v8.8 (demande d'Adel) : un humain derrière l'écran — l'animateur parle toutes les ~90 s quand rien d'autre ne passe, avec humour
  // v8.8 (demande d'Adel) : « mets le graphique sur ta télé / ton PC / ton mobile, le coach est avec toi »
  COACH.anim.push('📺 {m} : mets le graphique sur ta télé, ton PC ou ton mobile et patiente 😌 • le coach est avec toi • regarde le spectacle, partage • lien en bio la team 🙏', '🍿 {m} : installe-toi bien, le spectacle continue 🎬 • tapote, commente, partage • les infos avant tout le monde : lien en bio');
  EN.push([' : mets le graphique sur ta télé, ton PC ou ton mobile et patiente 😌 • le coach est avec toi • regarde le spectacle, partage • lien en bio la team 🙏', ': put the chart on your TV, PC or phone and be patient 😌 • the coach is with you • enjoy the show, share • link in bio team 🙏'], [' : installe-toi bien, le spectacle continue 🎬 • tapote, commente, partage • les infos avant tout le monde : lien en bio', ': get comfy, the show goes on 🎬 • tap, comment, share • the info before everyone: link in bio']);
  // v9.0 (demande d'Adel) : le spectateur voit la stratégie un moment, puis on l'invite à changer de marché / d'unité de temps (payant) : jamais de prix
  COACH.anim.push('🔁 {m} : tu préfères regarder le BTC ou le GOLD ? une autre unité de temps ? 👉 connecte-toi : lien en bio 😉', '👀 {m} : regarde bien la stratégie en entier… tu veux l\'autre marché ou une autre unité de temps ? 🔓 c\'est dans le lien en bio');
  EN.push([' : tu préfères regarder le BTC ou le GOLD ? une autre unité de temps ? 👉 connecte-toi : lien en bio 😉', ': would you rather watch BTC or GOLD? another timeframe? 👉 log in: link in bio 😉'], [' : regarde bien la stratégie en entier… tu veux l\'autre marché ou une autre unité de temps ? 🔓 c\'est dans le lien en bio', ': watch the whole strategy… want the other market or another timeframe? 🔓 it\'s in the link in bio']);
  COACH.humour = ["😂 {m} bouge moins que mon prof de maths le lundi matin… mais attention, ça va se réveiller 👀", "🤣 {m} : si tu tapotes pas, je mets la musique encore plus fort 🔊😄", "😎 {m} : moi je bois mon café, le marché prépare son coup… et toi tu fais quoi ? dis-le en commentaire 👇", "🫡 {m} : salut aux nouveaux qui arrivent ! installe-toi, regarde le spectacle, et tapote pour dire bonjour 👋", "🧐 {m} : je vois quelque chose se préparer… mais je le dis qu'à ceux qui sont dans la bio 😏", "💪 {m} : la team est là ? écris « PRÉSENT » en commentaire, je compte 👀"];
  EN.push([" bouge moins que mon prof de maths le lundi matin… mais attention, ça va se réveiller 👀", " moves less than my maths teacher on Monday morning… but careful, it's about to wake up 👀"], [" : si tu tapotes pas, je mets la musique encore plus fort 🔊😄", " if you don't tap, I turn the music up even louder 🔊😄"], [" : moi je bois mon café, le marché prépare son coup… et toi tu fais quoi ? dis-le en commentaire 👇", " I'm sipping my coffee, the market is plotting… what are you doing? tell me in the comments 👇"], [" : salut aux nouveaux qui arrivent ! installe-toi, regarde le spectacle, et tapote pour dire bonjour 👋", " hi to the newcomers! sit back, enjoy the show, and tap to say hello 👋"], [" : je vois quelque chose se préparer… mais je le dis qu'à ceux qui sont dans la bio 😏", " I can see something brewing… but I only tell those in the bio 😏"], [" : la team est là ? écris « PRÉSENT » en commentaire, je compte 👀", " is the team here? write « PRESENT » in the comments, I'm counting 👀"]);
  // v9.2 (demande d'Adel) : un vrai animateur qui prend le temps de parler aux abonnés quand le marché hésite
  COACH.conv = ['💬 {m} hésite… donnez-moi vos avis en commentaire : ça monte ou ça descend ? votre avis m\'intéresse 👇', '🙏 {m} : merci pour les tapotements la team ! continuez 👆 je lis tous vos commentaires 👀', '🔗 {m} : dites-moi maintenant… envoyez vos avis dans le lien en bio, je vous réponds 😉 • et là-bas tout arrive en temps réel ⚡'];
  EN.push([' hésite… donnez-moi vos avis en commentaire : ça monte ou ça descend ? votre avis m\'intéresse 👇', ' is hesitating… give me your opinion in the comments: up or down? I want to know 👇'], [' : merci pour les tapotements la team ! continuez 👆 je lis tous vos commentaires 👀', ': thanks for the taps team! keep going 👆 I read all your comments 👀'], [' : dites-moi maintenant… envoyez vos avis dans le lien en bio, je vous réponds 😉 • et là-bas tout arrive en temps réel ⚡', ': tell me now… send your opinion via the link in bio, I\'ll answer you 😉 • and there everything comes in real time ⚡']);
  let coachN = 0, convN = 0;
  const coachT = setInterval(() => {
    if (occupe || file.length || retour || Date.now() - derniereTend < 40000 || Date.now() - derniereCoach < 120000) return;   // v9.2 (demande d'Adel) : marché mou = on a le temps de parler, ~40 s   // les vraies infos du marché passent toujours avant
    const k3 = coachN % 3, P = k3 === 2 ? COACH.conv : k3 === 1 ? COACH.humour : COACH.anim;   // v9.2 : la discussion avec les abonnés suit son ordre (avis → merci → lien en bio)
    montrer((k3 === 2 ? P[convN++ % P.length] : P[Math.floor(coachN / 3) % P.length]).replace('{m}', nomMarche()), false, 1);
    coachN++; derniereCoach = Date.now();
  }, 15000);
  let iaPool = [], iaPools = {}, iaN = 0;
  EN.push(['⚡ UNE POSITION SE PRÉPARE • attends la confirmation, ne cours pas après le prix • lien en bio', '⚡ A TRADE IS GETTING READY • wait for confirmation, never chase price • link in bio']);
  // Une analyse IA doit être visible ET animée sur le graphique, sans recouvrir une annonce prioritaire.
  // La bulle, le ping sur le prix et la lueur neutre signalent un commentaire du coach, pas un signal d'entrée.
  function afficherIA(texte) {
    const phrase = String(texte || '').trim();
    if (!phrase || occupe || file.length) return false;
    montrer('🧠 ' + phrase, false, 2, 'membre', false, 'ia');
    coeurs(1, ['🧠', '📡']);
    lueur(0);
    return true;
  }
  function recuIA(json) {
    try {
      const donnees = JSON.parse(json);
      const propres = paires => (Array.isArray(paires) ? paires : [])
        .filter(p => Array.isArray(p) && p.length === 2 && typeof p[0] === 'string' && typeof p[1] === 'string' && !/\\d|telegram/i.test(p[0] + p[1]))
        .map(([fr, en]) => { const f = sansPrix(fr); if (!EN.some(e => e[0] === f)) EN.push([f, en]); return f; });
      if (Array.isArray(donnees)) {
        iaPools = {};
        iaPool = propres(donnees);
      } else if (donnees && typeof donnees === 'object') {
        iaPools = {};
        ['BTC', 'GOLD'].forEach(m => { iaPools[m] = propres(donnees[m]); });
        iaPool = iaPools[codeMarche()] || [];
      } else return;
      iaN = 0;
      // Affichage immédiat du premier commentaire pour le marché ouvert ; la suite reste espacée.
      const marche = codeMarche();
      const pool = Object.keys(iaPools).length ? (iaPools[marche] || []) : iaPool;
      if (pool.length && afficherIA(pool[0])) iaN = 1;
    } catch (e) {}
  }
  const iaT = setInterval(() => {
    if (occupe || file.length) return;   // jamais par-dessus une vraie info
    const m = codeMarche();
    const pool = Object.keys(iaPools).length ? (iaPools[m] || []) : iaPool;  // commentaires du marché affiché uniquement
    if (!pool.length) return;
    afficherIA(pool[iaN++ % pool.length]);
  }, 75 * 1000);
  let astuceN = 0;
  const astuceT = setInterval(() => {
    if (occupe || file.length) return;            // jamais par-dessus une vraie info (TP, SL, news…)
    montrer(ASTUCES[astuceN++ % ASTUCES.length], true, 2);
  }, 20 * 60 * 1000);

  // ───── télécommande 15 s ─────
  let retour = null;
  // zoom lisible sur téléphone (TikTok) : grosses bougies, prix au-dessus du tableau, place pour la bande
  // petites unités (1m à 5m) : prix cadré serré autour du dernier cours pour que ENTRÉE / SL / ZONE ne se chevauchent pas
  const SPAN = {};   // désactivé : le cadrage serré cachait ENTRÉE / SL (v67 : les étiquettes gênantes sont masquées sous 15 min)
  function dernierPrix() {
    const m = document.title.match(/\d[\d\s\u00a0\u202f]*,\d+/);
    return m ? parseFloat(m[0].replace(/[\s\u00a0\u202f]/g, '').replace(',', '.')) : NaN;
  }
  // v5.2 : si Adel change le zoom / la hauteur des prix, c'est retenu (même après rechargement) et le script ne le défait plus
  let PREF = { bar: 18, off: 10, manuelPrix: false };
  try { PREF = Object.assign(PREF, JSON.parse(localStorage.getItem('alignBandePref') || '{}')); } catch (e) {}
  function sauverPref() { try { localStorage.setItem('alignBandePref', JSON.stringify(PREF)); } catch (e) {} }
  function memoriser() { try {
    const c = chart(); if (!c) return;
    const ts = c.getTimeScale(), b = ts.barSpacing(), o = ts.rightOffset();
    if (b > 1 && b < 80) PREF.bar = b;
    if (o >= 0 && o <= 80) PREF.off = o;          // un retour dans l'historique n'est pas une préférence
    PREF.manuelPrix = !c.getPanes()[0].getMainSourcePriceScale().isAutoScale();
    sauverPref();
  } catch (e) {} }
  function cadrerPrix(c) {
    const ps = c.getPanes()[0].getMainSourcePriceScale();
    const k = SPAN[c.resolution()], p = dernierPrix();
    if (k && p > 0) { const e = p * k; ps.setAutoScale(false); ps.setVisiblePriceRange({ from: p - e * 0.55, to: p + e * 0.45 }); }
    else if (!ps.isAutoScale() && !PREF.manuelPrix) ps.setAutoScale(true);
  }
  function zoom(delai) {
    setTimeout(() => { try {
      const c = chart(); if (!c) return;
      c.applyOverrides({ 'scalesProperties.scaleSeriesOnly': false, 'paneProperties.topMargin': 16, 'paneProperties.bottomMargin': 38 });   // v5.0 : SL / TP inclus dans l'échelle, place pour le tableau en bas
      const ts = c.getTimeScale(); ts.setBarSpacing(PREF.bar); ts.setRightOffset(PREF.off);
      cadrerPrix(c);
      // l'indicateur ALIGN toujours DEVANT les bougies (étiquettes lisibles)
      const al = c.getAllStudies().filter(x => /^ALIGN/.test(x.name)).map(x => x.id); if (al.length) c.bringToFront(al);
    } catch (e) {} }, delai || 900);
  }
  zoom(300);
  // suivi automatique : même cadrage sur toutes les unités et marchés, le graphique suit le prix tout seul
  // (si Adel bouge le graphique à la souris, on lui laisse la main 20 s puis on recadre)
  let mainUser = 0;
  ['wheel', 'mousedown', 'touchstart'].forEach(ev => document.addEventListener(ev, e => {
    if (e.target && e.target.closest && (e.target.closest('.chart-markup-table') || e.target.closest('.price-axis') || e.target.closest('.time-axis'))) {
      mainUser = Date.now(); clearTimeout(memoriser.t); memoriser.t = setTimeout(memoriser, 1500);
    }
  }, { passive: true, capture: true }));
  // nouveau marché = autre échelle de prix → prix en automatique ; le zoom des bougies d'Adel est gardé
  try { const c0 = chart(); c0.onIntervalChanged().subscribe(null, () => zoom(1200)); c0.onSymbolChanged().subscribe(null, () => { PREF.manuelPrix = false; sauverPref(); zoom(1200); }); } catch (e) {}
  const suivi = setInterval(() => { try {
    if (Date.now() - mainUser < 20000) return;
    const c = chart(); if (!c) return;
    cadrerPrix(c);
    const ts = c.getTimeScale();
    if (Math.abs(ts.barSpacing() - PREF.bar) > 0.5) ts.setBarSpacing(PREF.bar);
    if (Math.abs(ts.rightOffset() - PREF.off) > 2) { ts.scrollToRealtime(); ts.setRightOffset(PREF.off); }
  } catch (e) {} }, 3000);
  // v12.2.11 : avec @grant, le script tourne isolé : l'API TradingView de la page est lue via unsafeWindow.
  const PAGE = (typeof unsafeWindow !== 'undefined' && unsafeWindow) ? unsafeWindow : window;
  function chart() { try { return PAGE.TradingViewApi.activeChart(); } catch (e) { return null; } }
  function commande(sorte, valeur, prenom) {
    const c = chart(); if (!c) return;
    if (!retour) retour = { tf: c.resolution(), sym: c.symbol() };
    const nom = prenom ? prenom + ' a demandé ' : 'Vue ';
    const fin = ' • ⏳ 15 s • 📸 fais ta capture';
    if (sorte === 'tf') { c.setResolution(valeur); montrer('🎮 ' + nom + (valeur === '60' ? '1 h' : valeur + ' min') + fin, true); }
    else if (sorte === 'sym') { c.setSymbol(valeur); montrer('🎮 ' + nom + valeur.split(':').pop() + fin, true); }
    else return;
    zoom();
    clearTimeout(commande.t);
    commande.t = setTimeout(() => {
      const c2 = chart(); if (c2 && retour) { const r0 = retour; c2.setSymbol(r0.sym, () => { c2.setResolution(r0.tf); zoom(); }); }
      retour = null;
    }, DUREE_MAIN);
  }

  // v4.9 : TP touché = explosion à l'écran (aucune info d'entrée : juste la fête, le coach reste dans le bot)
  const cssFeu = document.createElement('style');
  cssFeu.textContent = `#align-feu{position:fixed;inset:0;z-index:10000;pointer-events:none;display:flex;align-items:center;justify-content:center}
  #align-feu .titre{font:900 78px/1 system-ui,Segoe UI,Arial,sans-serif;color:#fff;text-shadow:0 0 18px #ff2d95,0 0 36px #1e90ff;animation:feuZoom 1.2s ease-out}
  #align-feu .eclat{position:absolute;font-size:46px;animation:feuVol 1.8s ease-out forwards}
  @keyframes feuZoom{0%{transform:scale(.2);opacity:0}60%{transform:scale(1.25);opacity:1}100%{transform:scale(1)}}
  @keyframes feuVol{0%{transform:translate(0,0) scale(.4);opacity:1}100%{transform:translate(var(--dx),var(--dy)) scale(1.3);opacity:0}}`;
  document.head.appendChild(cssFeu);
  function feuArtifice(titre) {
    try {
      document.getElementById('align-feu')?.remove();
      const f = document.createElement('div'); f.id = 'align-feu';
      f.innerHTML = '<div class="titre">' + esc(titre) + '</div>';
      const em = ['🎆', '🎇', '✨', '🔥', '💥', '🥳'];
      for (let i = 0; i < 28; i++) {
        const e = document.createElement('span'); e.className = 'eclat'; e.textContent = em[i % em.length];
        const a = (i / 28) * Math.PI * 2, d = 220 + Math.random() * 260;
        e.style.setProperty('--dx', Math.cos(a) * d + 'px'); e.style.setProperty('--dy', Math.sin(a) * d + 'px');
        e.style.animationDelay = (Math.random() * 0.4) + 's'; f.appendChild(e);
      }
      document.body.appendChild(f);
      setTimeout(() => f.remove(), 4500);
    } catch (e) {}
  }
  window.__ALIGN_FEU__ = feuArtifice;
  // v5.7 : TP touché = pluie de billets et de pièces sur l'écran, « ÇA ENCAISSE 💰 »
  const cssBillet = document.createElement('style');
  cssBillet.textContent = `.align-billet{position:fixed;z-index:10000;pointer-events:none;font-size:44px;top:-60px;animation:billetTombe var(--t) linear forwards}
  @keyframes billetTombe{0%{transform:translate(0,0) rotate(0)}100%{transform:translate(var(--dx),var(--h)) rotate(var(--rot));opacity:.2}}`;
  document.head.appendChild(cssBillet);
  function pluieBillets(n) {
    try {
      const r = zoneGraphique(), H = (r.height || 700) + 120, em = ['💵', '💰', '💸', '🪙', '💶', '🤑'];
      for (let i = 0; i < (n || 40); i++) setTimeout(() => {
        const e = document.createElement('span'); e.className = 'align-billet'; e.textContent = em[(Math.random() * em.length) | 0];
        e.style.left = (r.left + Math.random() * (r.width - 90)) + 'px'; e.style.top = r.top + 'px';
        e.style.setProperty('--t', (2.2 + Math.random() * 1.6) + 's'); e.style.setProperty('--h', H + 'px');
        e.style.setProperty('--dx', (Math.random() * 120 - 60) + 'px'); e.style.setProperty('--rot', (Math.random() * 720 - 360) + 'deg');
        document.body.appendChild(e); setTimeout(() => e.remove(), 4200);
      }, i * 70);
    } catch (e) {}
  }
  window.__ALIGN_BILLETS__ = pluieBillets;
  // v6.8 (demande d'Adel) : prix sur l'objectif = EXPLOSION D'ARGENT dans le sens du marché
  //   marché qui coule (sens -1) → éclat au niveau du prix puis l'argent retombe en pluie ;
  //   marché qui monte (sens +1) → éclat puis l'argent s'envole vers le haut. Jamais de fusée quand ça coule.
  const cssArgent = document.createElement('style');
  cssArgent.textContent = `.align-argent{position:fixed;z-index:10001;pointer-events:none;font-size:46px;animation:argentVole var(--t) cubic-bezier(.15,.8,.3,1) forwards}
  @keyframes argentVole{0%{transform:translate(0,0) scale(.3) rotate(0);opacity:1}25%{transform:translate(var(--ex),var(--ey)) scale(1.2)}
    100%{transform:translate(var(--dx),var(--dy)) scale(1) rotate(var(--rot));opacity:0}}
  #align-flash-or{position:fixed;inset:0;z-index:9999;pointer-events:none;background:radial-gradient(circle at var(--x) var(--y),rgba(255,215,0,.55),rgba(255,215,0,0) 45%);animation:flashOr 1.2s ease-out forwards}
  @keyframes flashOr{from{opacity:1}to{opacity:0}}`;
  document.head.appendChild(cssArgent);
  function explosionArgent(sens) {
    try {
      const r = zoneGraphique(), x0 = r.left + r.width * 0.72, y0 = r.top + (r.height || 700) * 0.55, em = ['💵', '💰', '💸', '🪙', '💶', '🤑', '💎'];
      const f = document.createElement('div'); f.id = 'align-flash-or'; f.style.setProperty('--x', x0 + 'px'); f.style.setProperty('--y', y0 + 'px');
      document.getElementById('align-flash-or')?.remove(); document.body.appendChild(f); setTimeout(() => f.remove(), 1300);
      for (let i = 0; i < 46; i++) {
        const e = document.createElement('span'); e.className = 'align-argent'; e.textContent = em[i % em.length];
        const a = Math.random() * Math.PI * 2, rr = 60 + Math.random() * 140;
        e.style.left = x0 + 'px'; e.style.top = y0 + 'px';
        e.style.setProperty('--ex', Math.cos(a) * rr + 'px'); e.style.setProperty('--ey', Math.sin(a) * rr + 'px');
        e.style.setProperty('--dx', (Math.cos(a) * rr * 1.6) + 'px');
        e.style.setProperty('--dy', (sens === -1 ? 380 + Math.random() * 260 : -(380 + Math.random() * 260)) + 'px');
        e.style.setProperty('--rot', (Math.random() * 540 - 270) + 'deg'); e.style.setProperty('--t', (2.2 + Math.random() * 1.2) + 's');
        e.style.animationDelay = (Math.random() * 0.25) + 's';
        document.body.appendChild(e); setTimeout(() => e.remove(), 3800);
      }
    } catch (e) {}
  }
  window.__ALIGN_ARGENT__ = explosionArgent;

  // v9.9 (demande d'Adel) : fenêtre « 💰 ALIGN EN DIRECT » = gain RÉEL en cours des comptes du bot.
  // Le bot ne l'envoie que lorsque le prix a fait la moitié du chemin vers le TP1 (trop tard pour entrer) et qu'il y a de vraies positions.
  const pnlCss = document.createElement('style'); pnlCss.textContent = `
  #align-pnl{position:fixed;z-index:141;top:96px;right:90px;pointer-events:none;padding:10px 16px;border-radius:14px;color:#fff;
    font:900 22px/1.15 system-ui,Segoe UI,Arial,sans-serif;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.5);border:2px solid rgba(255,255,255,.35);
    animation:pnlPouls 1.4s ease-in-out infinite alternate}
  #align-pnl small{display:block;font-size:12px;font-weight:800;opacity:.9;letter-spacing:.5px}
  @keyframes pnlPouls{from{transform:scale(1)}to{transform:scale(1.06)}}
  html.align-cache #align-pnl{visibility:hidden!important}`; document.head.appendChild(pnlCss);
  function fenetrePnl(v, m) {
    let b = document.getElementById('align-pnl');
    if (v === 'off' || isNaN(parseFloat(v))) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement('div'); b.id = 'align-pnl'; document.body.appendChild(b); }
    const x = parseFloat(v), en = langueBande() === 'en';
    b.style.background = x >= 0 ? 'linear-gradient(135deg,#0f9d58,#0b7a43)' : 'linear-gradient(135deg,#c62828,#8e1b1b)';
    b.innerHTML = '<small>' + (en ? '💰 ALIGN LIVE • REAL ACCOUNTS • ' : '💰 ALIGN EN DIRECT • VRAIS COMPTES • ') + esc(m || '') + '</small>'
      + (x >= 0 ? '+' : '−') + Math.abs(x).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' $'
      + '<small>' + (en ? 'Do not enter late • next setup: link in bio' : 'Ne rentre pas en retard • prochaine configuration : lien en bio') + '</small>';
  }
  function recu(txt) {
    txt = String(txt || '').trim(); if (!txt) return;
    botSuivi(txt);                                                               // v8.5 : le bot est-il VRAIMENT en position ?
    if (txt.startsWith('IA:')) { recuIA(txt.slice(3)); return; }
    if (/LIKES ATTEINT/i.test(txt)) { feuArtifice('🎆 BRAVO LA TEAM !'); coeurs(20, ['❤️', '🎉', '🔥']); }   // v8.8 : objectif de likes validé depuis l'admin                 // v8.5 : lot de phrases IA
    if (txt.startsWith('CMD:chrono:')) {                                          // v8.5 : « une position arrive » + chrono
      const sec = Math.min(900, Math.max(30, parseInt(txt.split(':')[2], 10) || 0));
      window.__ALIGN_POS__ = { fin: Date.now() + sec * 1000 };
      montrer('⚡ UNE POSITION SE PRÉPARE • attends la confirmation, ne cours pas après le prix • lien en bio', false, 1, 'proche', true);
      return;
    }
    if (txt.startsWith('NEWS:')) {   // v10.6 (demande d'Adel) : news de dernière minute → la bande est COUPÉE et passe la news en priorité
      const [fr, en] = txt.slice(5).split('|'); const t = '🚨 NEWS DE DERNIÈRE MINUTE : ' + (fr || '').trim() + ' • le marché peut bouger fort • détails : lien en bio';
      EN.push([t, '🚨 BREAKING NEWS: ' + (en || fr || '').trim() + ' • the market can move hard • details: link in bio']);
      montrer(t, false, 2, 'danger', true); coeurs(1, ['📢']); return;
    }
    if (txt.startsWith('CMD:pnl:')) { fenetrePnl(txt.split(':')[2], txt.split(':')[3]); return; }   // v9.9 : gain réel en cours
    if (txt.startsWith('CMD:plateforme:')) {          // le bot peut basculer la bande : tiktok / youtube / les2
      const v = txt.split(':')[2]; if (['tiktok', 'youtube', 'les2'].includes(v)) choisirPlateforme(v); return;
    }
    if (txt.startsWith('CMD:')) {
      const p = txt.split(':');               // CMD:sorte:valeur(:avec:deux-points):prénom
      const sorte = p[1], prenom = p[p.length - 1], valeur = p.slice(2, -1).join(':');
      commande(sorte, valeur, prenom); return;
    }
    const bulle = txt.startsWith('BULLE:');
    if (bulle) txt = txt.slice(6).trim();
    // v8.0 (demande d'Adel) : un abonné booste le live depuis le bot → son prénom passe TOUT DE SUITE, avec feu d'artifice et merci
    if (/BOOSTE LE LIVE/i.test(txt)) { const pr = ((txt.match(/MERCI\s+([^!]+)!/i) || [])[1] || '').trim(); montrer(txt, false, 1, 'membre', true); feuArtifice('🚀 MERCI ' + pr.toUpperCase() + ' !'); setTimeout(() => coeurs(1, ['🙏']), 2500); return; }
    if (/POSITION ALIGN CONFIRMÉE|ENTRE EN POSITION/i.test(txt)) { feuArtifice('🚀 POSITION CONFIRMÉE !'); coeurs(12, ['🚀', '🔥', '💚']); }
    if (/TP\d? TOUCH|OBJECTIF FINAL|TP2 TOUCH/i.test(txt)) { feuArtifice(/TP2|FINAL/i.test(txt) ? '🏆 ÇA ENCAISSE !' : '💰 ÇA ENCAISSE !'); pluieBillets(45);
      // v10.0 (demande d'Adel) : un TP mérite un petit cadeau → on invite à liker / envoyer une rose, sans jamais forcer
      setTimeout(() => montrer('🌹 LA TEAM VIENT D\'ENCAISSER ! si t\'as kiffé, une petite rose ou un like ❤️ ça motive le coach • merci à ceux qui gâtent le live 🎁', false, 1, 'membre', true), 9000);
      setTimeout(() => montrer('🆓 TOI AUSSI TU VEUX ENCAISSER AVEC LA TEAM ? crée ton compte démo GRATUIT et active ton coach • lien en bio • ce n\'est pas un conseil en investissement', false, 1, 'membre', true), 22000); }
    if (/\bSL\b[^\n]{0,12}TOUCH|STOP TOUCH/i.test(txt)) setTimeout(() => coeurs(1, ['😢']), 3600);
    if (/PLONGE|DIVING/i.test(txt)) { coeurs(1, ['🌊']); setTimeout(() => coeurs(1, ['😄']), 5000); }   // v10.7 : quand ça coule aussi
    else if (/ACCÉLÈRE|SPEEDING UP|DIRECTION TP|ENTRE EN POSITION|POSITION ALIGN CONFIRMÉE/i.test(txt)) { coeurs(1, ['🚀']); setTimeout(() => coeurs(1, ['😄']), 5000); }   // v10.5 (Adel) : fusée quand ça part fort + sourire   // v7.1 : smiley triste, on se refait
    montrer(txt, bulle, 2, '', false, bulle ? 'marche' : 'live');   // Les messages BULLE du marché sont aussi narrés ; messages ordinaires restent muets
    const em = (txt.slice(0, 4).match(/🔮|🧱|🛏/) || [])[0]; if (em) setTimeout(() => coeurs(1, [em]), 1500);   // v7.3 : animation « le graphique parle »
  }

  // ───── écoute du canal ntfy (reconnexion automatique) ─────
  let es;
  // v12.2.11 : le heartbeat passe par GM_xmlhttpRequest (hors de la page TradingView, sans CORS ni blocage réseau de la page).
  // Repli sur fetch si le gestionnaire de scripts ne fournit pas GM_xmlhttpRequest.
  function envoyerEcran(corps) {
    const url = 'https://ntfy.sh/' + SUJET + '-ecran';
    try {
      if (typeof GM_xmlhttpRequest === 'function') {
        GM_xmlhttpRequest({ method: 'POST', url: url, data: corps, timeout: 8000, onerror: () => {}, ontimeout: () => {} });
      } else {
        fetch(url, { method: 'POST', body: corps, keepalive: true }).catch(() => {});
      }
    } catch (e) {}
  }
  function pingEcran() {
    envoyerEcran('PING|LIVE_SCREEN|' + Date.now());
  }
  function ecouter() {
    try { es && es.close(); } catch (e) {}
    es = new EventSource('https://ntfy.sh/' + SUJET + '/sse');
    es.onopen = pingEcran;
    es.onmessage = e => { try { const d = JSON.parse(e.data); if (d.event === 'message') recu(d.message); } catch (er) {} };
    es.onerror = () => { try { es.close(); } catch (e) {} setTimeout(ecouter, 5000); };
  }
  ecouter();
  pingEcran();
  const heartbeatT = setInterval(pingEcran, 25000);

  // ───── infobulles : baissier → en haut, haussier → en bas, collées à gauche ─────
  // v6.2 (demande d'Adel) : plus de petite fenêtre au survol : l'explication de la ligne (ENTRÉE, SL, TP, ZONE…)
  // passe dans la BANDE qui défile, 2 fois, avec la couleur de la ligne (TP vert/or, SL rouge, entrée orange)
  const vuTT = {};
  function teaserLigne(t) {
    const c = couleurLigne(t);
    return c === 'tp' ? '👀 Zone clé : le marché pourrait y souffler… ce qu\'il prépare : 📲 lien en bio 🎁'
      : c === 'sl' ? '👀 Zone clé : le marché teste la patience de tout le monde… 📲 lien en bio 🎁'
      : '👀 Zone clé du marché • ce qu\'elle annonce : 📲 lien en bio 🎁';
  }
  function couleurLigne(t) { const h = String(t).slice(0, 28); return /\bSL\b|STOP/.test(h) ? 'sl' : /TP/.test(h) ? 'tp' : /ENTR/.test(h) ? 'alerte' : 'membre'; }   // la couleur suit le DÉBUT du texte (le nom de la ligne)
  function texteLigne(t) { return String(t || '').replace(/[━─]+/g, ' ').replace(/\s*\n+\s*/g, ' • ').replace(/(\s•\s)+/g, ' • ').replace(/^\s*•\s*|\s*•\s*$/g, '').trim(); }
  const obs = new MutationObserver(() => {
    document.querySelectorAll('[class*="common-tooltip-"][class*="common-tooltip--"]').forEach(t => {
      const txt = t.innerText || '';
      if (!/[━]|ENTRÉE|SL|TP|ZONE|RETOURNEMENT|CONFIRMATION/.test(txt)) return;
      t.style.visibility = 'hidden';                 // la fenêtre ne s'affiche plus : tout passe dans la bande
      const ligne = texteLigne(txt), now = Date.now();
      if (ligne && now - (vuTT[ligne] || 0) > 45000 && now - (window.__alignExpl || 0) > 5000) { vuTT[ligne] = now; montrer(teaserLigne(ligne), false, 2, couleurLigne(ligne)); }
    });
  });
  obs.observe(document.body, { childList: true, subtree: true });

  // ───── v5.5 : LE SPECTACLE — la bande regarde l'écran elle-même ─────
  // Elle lit les bougies affichées (marché + unité de la vue) et anime le live : accélération, cassure, gros volume,
  // compte à rebours de clôture, tendance, cœurs qui montent. JAMAIS un prix ni un niveau, jamais le mot Telegram :
  // juste le spectacle + « lien en bio ». Les vraies infos précises restent dans le privé (bot).
  const cssShow = document.createElement('style');
  cssShow.textContent = `
  #align-show{position:fixed;z-index:10001;pointer-events:none;display:none;align-items:center;gap:14px;padding:10px 26px;
    border-radius:18px;font:900 40px/1.1 system-ui,Segoe UI,Arial,sans-serif;color:#fff;white-space:nowrap;
    text-shadow:0 3px 6px rgba(0,0,0,.55);box-shadow:0 8px 30px rgba(0,0,0,.55);transform:translateX(-50%)}
  #align-show.go{display:flex;animation:showPop 2.8s cubic-bezier(.2,1.4,.4,1) forwards}
  #align-show.bas{background:linear-gradient(90deg,#ff1744,#ff6d00)} #align-show.haut{background:linear-gradient(90deg,#00c853,#00e5ff);color:#000;text-shadow:none}
  #align-show.neutre{background:linear-gradient(90deg,#8a2be2,#ff2d95)}
  #align-show .emo{font-size:54px;animation:showBat .5s ease-in-out infinite alternate}
  @keyframes showPop{0%{opacity:0;transform:translateX(-50%) scale(.3)}15%{opacity:1;transform:translateX(-50%) scale(1.12)}
    25%{transform:translateX(-50%) scale(1)}85%{opacity:1}100%{opacity:0;transform:translateX(-50%) scale(.9) translateY(-14px)}}
  @keyframes showBat{from{transform:scale(1)}to{transform:scale(1.25)}}
  #align-cadre{position:fixed;z-index:9998;pointer-events:none;border-radius:8px;opacity:0}
  #align-cadre.go{animation:cadreFlash 1.6s ease-out 2}
  @keyframes cadreFlash{0%{opacity:0}20%{opacity:1}100%{opacity:0}}
  #align-chrono{position:fixed;z-index:10001;pointer-events:none;display:none;flex-direction:column;align-items:center;
    padding:8px 18px;border-radius:16px;background:rgba(0,0,0,.72);border:3px solid #ffd400;color:#ffd400;
    font:900 46px/1 system-ui,Segoe UI,Arial,sans-serif;text-align:center}
  #align-chrono small{font:800 17px/1.3 system-ui,Segoe UI,Arial,sans-serif;color:#fff;animation:chronoClignote .8s steps(2,start) infinite}
  @keyframes chronoClignote{to{visibility:hidden}}
  #align-chrono.urgent{border-color:#ff2d95;color:#ff2d95;animation:showBat .4s ease-in-out infinite alternate}
  .align-coeur{position:fixed;z-index:9997;pointer-events:none;font-size:38px;animation:coeurMonte 3.2s ease-out forwards}
  @keyframes coeurMonte{0%{opacity:0;transform:translate(0,0) scale(.5)}15%{opacity:1}
    100%{opacity:0;transform:translate(var(--dx),-340px) scale(1.3) rotate(var(--rot))}}`;
  document.head.appendChild(cssShow);
  const cadre = document.createElement('div'); cadre.id = 'align-cadre'; document.body.appendChild(cadre);
  const chrono = document.createElement('div'); chrono.id = 'align-chrono'; document.body.appendChild(chrono);

  function nomMarche() {
    const s = String((chart() && chart().symbol()) || '');
    return /BTC/i.test(s) ? '🟠 BTC' : /XAU|GOLD/i.test(s) ? '🥇 GOLD' : '📊 ' + s.split(':').pop();
  }
  function barres(n) {
    try {
      const b = chart()._chartWidget.model().mainSeries().bars(), fin = b.lastIndex(), out = [];
      for (let i = Math.max(b.firstIndex(), fin - (n || 60) + 1); i <= fin; i++) { const v = b.valueAt(i); if (v) out.push(v); }
      return out;                                   // [temps, ouverture, haut, bas, clôture, volume]
    } catch (e) { return []; }
  }
  // v5.5 (demande d'Adel) : le spectacle passe DANS la bande, en défilant comme les autres infos (rouge = ça baisse, vert = ça monte)
  function pop(emo, texte, sens, suite) {
    montrer(emo + ' ' + texte + (suite ? ' • ' + suite : ''), false, 1, sens === -1 ? 'bas' : sens === 1 ? 'haut' : 'membre');
  }
  function lueur(sens) {
    try {
      const r = zoneGraphique(), col = sens === -1 ? '#ff1744' : sens === 1 ? '#00e676' : '#ff2d95';
      Object.assign(cadre.style, { left: r.left + 'px', top: r.top + 'px', width: (r.width - 70) + 'px', height: (r.height || 600) + 'px',
        boxShadow: 'inset 0 0 60px 12px ' + col, border: '4px solid ' + col });
      cadre.classList.remove('go'); void cadre.offsetWidth; cadre.classList.add('go');
    } catch (e) {}
  }
  // v6.9 (demande d'Adel) : plus de petits émojis qui s'envolent (on ne comprend pas ce que c'est) → UNE punchline pro
  // dans une pastille qui monte doucement, en français avec l'anglais dessous. Le contexte choisit la phrase.
  // v7.0 (demande d'Adel) : quand le marché se réveille, on remercie les tapotements avec un petit mot qui fait sourire (jamais 2 fois le même d'affilée) ;
  // quand le prix arrive sur une zone clé : « rentrer ou couper ? » + abonne-toi, lien en bio (jamais de prix ni TP/SL sur la bande).
  const PUNCH = [
    [/🌊/, ['🌊 Ça plonge, accrochez-vous !', '🌊 It\'s diving, hold on tight!'], ['🎢 Descente express, qui est à bord ?', '🎢 Express drop, who\'s on board?'], ['🌊 Ça coule fort, tapote si t\'es dedans 👆', '🌊 Sinking hard, tap if you\'re in 👆']],   // v10.7
    [/🚀/, ['🚀 Ça décolle, accrochez-vous !', '🚀 Lift-off, hold on tight!'], ['🚀 La fusée est partie 😎 qui est à bord ?', '🚀 The rocket took off 😎 who\'s on board?'], ['🚀 Ça part fort, tapote si t\'es dedans 👆', '🚀 It\'s flying, tap if you\'re in 👆']],   // v10.5
    [/😄/, ['😄 Le sourire de ceux qui ont attendu le feu vert', '😄 The smile of those who waited for the green light'], ['😄 Ça fait plaisir à voir, la team !', '😄 Love to see it, team!']],
    [/💥/, ['🎯 Objectif atteint d\'un coup !', '🎯 Target hit in one go!'], ['🚀 Objectif pris, la team encaisse !', '🚀 Target taken, the team cashes in!'], ['🔥 On a encaissé, c\'est le feu', '🔥 Cashed in, it\'s fire']],
    // v7.4 : position en cours dans le bon sens → on fait sourire (sans prix)
    [/😊/, ['😊 Vous êtes contents ? Je vous demande rien…', '😊 Happy? I ask for nothing…'], ['🙏 Juste tapoter l\'écran et partager', '🙏 Just tap the screen and share'], ['😄 Ça roule pour la team ALIGN', '😄 Smooth ride for team ALIGN']],
    [/😏/, ['😏 Je plains ceux en contre-tendance…', '😏 Feeling sorry for the counter-trend crowd…'], ['💪 On continue dans le sens du marché', '💪 We keep riding the trend'], ['🤭 Pendant ce temps, à contre-sens…', '🤭 Meanwhile, the wrong-way crowd…']],
    // v7.3 : le graphique « parle » quand le coach annonce une zone (🔮 approche, 🧱 / 🛏 contact)
    [/🔮/, ['🔮 Ça va tester !', 'Testing soon!'], ['👀 Zone en approche', 'Zone incoming'], ['🎯 Le marché vise une zone', 'Market eyeing a zone']],
    [/🧱|🛏/, ['🧱 Ça bute !', 'Hitting a wall!'], ['🎯 Zone touchée', 'Zone touched'], ['😮 Contact !', 'Contact!']],
    // v7.1 : objectif de protection touché → un smiley triste qui relativise (jamais le mot SL ni de prix sur la bande)
    [/😢/, ['😢 Pas cette fois…', 'Not this time…'], ['😔 Ça arrive, on se refait 💪', 'It happens, we bounce back 💪'],
      ['🥲 Le marché a gagné cette manche', 'The market won this round'], ['🧠 Le bot apprend de chaque trade', 'The bot learns from every trade'],
      ['🙃 C\'est pas grave, on le récupère', 'No big deal, we\'ll get it back']],
    [/⏰/, ['⏰ Vos tapotements ont réveillé le marché 😄', 'Your taps woke up the market'], ['👆 Continuez de tapoter, ça le réveille 😜', 'Keep tapping, it wakes it up'],
      ['😳 Le marché s\'est réveillé !', 'The market just woke up!'], ['⚡ La team ALIGN a remis le courant 😎', 'Team ALIGN turned the power back on'],
      ['🥁 Ça bouge enfin ! Merci les tapoteurs 😁', 'Finally moving! Thanks, tappers'], ['☕ Le marché a bu son café 😅', 'The market had its coffee'],
      ['🔔 Debout là-dedans ! 🤣', 'Wakey wakey! 🤣'], ['😏 Vous l\'avez secoué !', 'You shook it up 😏']],
    [/🤔/, ['🤔 Rentrer ou couper ? 😏', 'In or out? • abonne-toi / follow : lien en bio 🎁'], ['👀 Tu dois couper ta position ? 😬', 'Cut or hold? • abonne-toi / follow : lien en bio 🎁'],
      ['🎯 Rentrer maintenant ou attendre ? 🤫', 'Enter now or wait? • abonne-toi / follow : lien en bio 🎁'], ['😅 Garder ou couper ? Le coach sait 😉', 'Hold or cut? The coach knows • lien en bio 🎁']],
    [/🪤|🎣|🪶/, ['🪤 Piège en cours', 'Trap in progress'], ['🎣 Qui va mordre ?', 'Who takes the bait?']],
    [/🐋|💰/, ['🐋 Les baleines arrivent', 'Whales incoming'], ['👀 Gros volume', 'Big volume']],
    [/📉|🔴|🌊/, ['📉 La pression vend', 'Sellers in control'], ['🔴 Ça pousse en bas', 'Pushing lower']],
    [/🙏/, ['🙏 Merci pour le boost !', '🙏 Thanks for the boost!'], ['🚀 Le live décolle grâce à toi', '🚀 The live takes off thanks to you'], ['💜 Toi t\'es un vrai', '💜 You\'re a real one']],
    // v8.0 : on fait parler le public (commentaires)
    [/💬/, ['💬 Tu rentres ou t\'attends ?', '💬 In or wait?'], ['😏 Envie de rentrer là ?', '😏 Tempted to jump in?'], ['📝 Ça monte ou ça descend ? Commente !', '📝 Up or down? Comment!'], ['🎯 Le plan est déjà prêt 😉', '🎯 The plan is already set 😉']],
    [/📈|🟢|🚀/, ['📈 Les acheteurs poussent', 'Buyers in control'], ['🟢 Ça pousse en haut', 'Pushing higher']],
    [/📲|🔌|📡|🧠/, ['📲 Connecté en temps réel', '📲 Connected in real time'], ['📡 En direct sur ton portable', '📡 Live on your phone']],
    [/🔄/, ['🔄 Changement de programme !', '🔄 Change of plan!'], ['🧭 On suit le marché', '🧭 We follow the market']],
    [/🏦/, ['🏦 Les gros sont là', '🏦 Big players here'], ['👀 Zone des gros', '👀 Smart-money zone']],
    [/🧲/, ['🧲 Le marché comble le trou', '🧲 Filling the gap'], ['👀 Zone aimant', '👀 Magnet zone']],
    // v7.6 (demande d'Adel) : on nargue avec humour quand une annonce se prépare (pro, sûr de lui)
    [/📢/, ['📢 Annonce à venir… 😏', '📢 Announcement coming… 😏'], ['🤫 Le coach sait déjà où ça va', '🤫 The coach already knows'], ['😎 Toi tu regardes, eux ils sont prévenus', '😎 You watch, they get the alert'], ['🧐 Décision prise. Lien en bio', '🧐 Decision made. Link in bio'], ['🧘 Attends le feu vert, ne cours pas après le prix', '🧘 Wait for confirmation, never chase price'], ['⏳ Une entrée arrive peut-être, on attend la confirmation', '⏳ A setup may be coming; wait for confirmation']],
    [/↩️/, ['↩️ Rebond sur zone clé', 'Bounce on key zone'], ['👀 Réaction du marché', 'Market reaction']],
    [/👆/, ['👆 Tapote, le marché dort encore 😴', '👆 Tap, the market is still asleep 😴'], ['😅 Pas d\'entrée ? Tapote en attendant', '😅 No entry yet? Tap meanwhile'], ['🫵 Toi là, tapote un peu 😄', '🫵 Hey you, give it a tap 😄']],
    [/./, ['❤️ Tapote l\'écran', 'Tap the screen'], ['🔔 Abonne-toi', 'Follow'], ['💪 La team ALIGN', 'Team ALIGN'], ['🎯 Reste concentré', 'Stay focused']]
  ];
  const cssPunch = document.createElement('style');
  cssPunch.textContent = `.align-punch{position:fixed;z-index:9997;pointer-events:none;padding:10px 22px;border-radius:999px;text-align:center;white-space:normal;max-width:min(430px,62vw);box-sizing:border-box;
    background:linear-gradient(90deg,#ff2d95,#8a2be2,#1e90ff);color:#fff;font:900 30px/1.15 system-ui,Segoe UI,Arial,sans-serif;
    box-shadow:0 6px 18px rgba(0,0,0,.45);text-shadow:0 2px 3px rgba(0,0,0,.4);animation:punchMonte 7.9s ease-out forwards}
  .align-punch.en{background:linear-gradient(90deg,#0d47a1,#1e88e5,#00bcd4)}
  #align-bande .flash.en{filter:hue-rotate(35deg) saturate(1.15)}
  .align-punch .emo{display:inline-block;animation:emoDanse .45s ease-in-out infinite alternate}
  @keyframes emoDanse{0%{transform:rotate(-14deg) scale(1)}100%{transform:rotate(14deg) scale(1.3)}}
  .align-punch small{display:block;font:700 17px/1.2 system-ui,Segoe UI,Arial,sans-serif;opacity:.9}
  @keyframes punchMonte{0%{opacity:0;transform:translateY(20px) scale(.7)}15%{opacity:1;transform:translateY(0) scale(1.05)}
    25%{transform:scale(1)}80%{opacity:1}100%{opacity:0;transform:translateY(-12px)}}
  /* v7.6 (demande d'Adel) : on a l'impression de PARLER avec le marché : bulle de BD qui pointe vers le prix, le texte s'écrit */
  .align-punch{border-radius:22px;animation:punchMonte 7.9s ease-out forwards,bulleRespire 1.6s ease-in-out .9s infinite alternate}
  .align-punch .qui{display:block;font:900 15px/1.2 system-ui,Segoe UI,Arial,sans-serif;letter-spacing:1px;opacity:.95;margin-bottom:2px}
  .align-punch .txt{display:inline-block;animation:sEcrit 1.1s steps(26,end) both}
  @keyframes sEcrit{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
  @keyframes bulleRespire{from{filter:brightness(1)}to{filter:brightness(1.18)}}
  .align-punch::after{content:'';position:absolute;right:var(--q,60px);border:14px solid transparent}
  .align-punch.dessus::after{top:100%;border-top-color:#1e90ff}
  .align-punch.dessous::after{bottom:100%;border-bottom-color:#1e90ff}
  .align-punch.en.dessus::after{border-top-color:#00bcd4} .align-punch.en.dessous::after{border-bottom-color:#00bcd4}
  .align-ping{position:fixed;z-index:9996;pointer-events:none;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;
    border:4px solid #ffd400;box-shadow:0 0 18px #ffd400;animation:pingPrix 1.1s ease-out 3 forwards}
  @keyframes pingPrix{0%{transform:scale(.4);opacity:1}100%{transform:scale(2.6);opacity:0}}`;
  cssPunch.textContent += `
  html.align-cache #align-bande,html.align-cache .align-punch,html.align-cache .align-ping,html.align-cache #align-chrono,html.align-cache #align-show,html.align-cache #align-cadre{visibility:hidden!important}`;   // v7.9
  document.head.appendChild(cssPunch);
  let punchN = 0, punchTok = 0;   // v7.5 : l'anglais d'une ancienne pastille n'efface plus la nouvelle
  // v7.5 (demande d'Adel) : sens de la pastille = celui de l'info (📉 baisse → en HAUT, 📈 hausse → en BAS), sinon la pente récente
  function sensPastille(cle) {
    if (/📉|🔴|🌊|😢|🚨/.test(cle)) return -1; if (/📈|🟢|🚀|💥|😊/.test(cle)) return 1;
    try { const B = barres(10); return B[B.length - 1][4] >= B[0][4] ? 1 : -1; } catch (e) { return 1; }
  }
  // v7.6 (demande d'Adel) : la pastille se met DANS la zone du prix (pas sur le côté, coupé sur téléphone) :
  // ça baisse → juste AU-DESSUS du prix (les bougies descendent), ça monte → juste EN DESSOUS ; jamais sur le chrono ni sur une autre info
  function pointPrix() {
    try { const r = zoneGraphique(), ser = chart()._chartWidget.model().mainSeries(), ps = ser.priceScale(), fv = ser.firstValue(), b = ser.bars();
      const last = b.valueAt(b.lastIndex()); let x = null;
      try { x = r.left + chart()._chartWidget.model().timeScale().indexToCoordinate(b.lastIndex()); } catch (er) {}
      return { x: isFinite(x) ? x : r.left + r.width - 220, y: r.top + ps.priceToCoordinate(last[4], fv) }; } catch (e) { return null; }
  }
  function chevauche(a, b) { return a.left < b.right + 8 && a.right > b.left - 8 && a.top < b.bottom + 8 && a.bottom > b.top - 8; }
  function placerPastille(e, sens) {
    const r = zoneGraphique(), H = r.height || 600, w = e.offsetWidth, h = e.offsetHeight, haut = r.top + 96, bas = r.top + H - 250 - h;   // v12.2.9 : réserve 250 px pour le tableau de bord des unités (la bulle ne le recouvre plus)
    const P = pointPrix();
    let left = Math.max(r.left + 10, r.left + r.width - 70 - w - 14);
    if (P && P.x > r.left + 60 && P.x < r.left + r.width - 70) left = Math.max(r.left + 10, Math.min(P.x - w + 70, r.left + r.width - 70 - w - 14));   // la pointe vise la dernière bougie
    let top = P ? (sens < 0 ? P.y - 46 - h : P.y + 46) : (sens < 0 ? haut : bas);
    if (top < haut) top = P ? P.y + 46 : haut; if (top > bas) top = P ? P.y - 46 - h : bas;   // pas de place d'un côté → de l'autre côté du prix
    if (e.dataset.bas) { top = bas; left = Math.max(r.left + 10, r.left + r.width - 70 - w - 14); }   // v8.1 (demande d'Adel) : motivation = en bas, juste au-dessus du tableau des unités, côté prix
    top = Math.max(haut, Math.min(top, bas));
    const obst = [chrono, document.getElementById('align-show')].filter(o => o && getComputedStyle(o).display !== 'none').map(o => o.getBoundingClientRect());
    for (let k = 0; k < 4; k++) { const box = { left, right: left + w, top, bottom: top + h }, o = obst.find(c => chevauche(box, c)); if (!o) break;
      top = sens < 0 ? o.top - h - 10 : o.bottom + 10; if (top < haut || top > bas) { left = Math.max(r.left + 10, o.left - w - 12); top = Math.max(haut, Math.min(top, bas)); } }
    e.style.left = left + 'px'; e.style.top = top + 'px';
    const dessus = P ? top + h / 2 < P.y : sens < 0; e.classList.toggle('dessus', dessus); e.classList.toggle('dessous', !dessus);
    if (P) e.style.setProperty('--q', Math.max(18, Math.min(w - 46, left + w - P.x - 14)) + 'px');
  }
  function ping() {   // v7.6 : un cercle jaune « bat » sur le prix quand le marché parle
    const P = pointPrix(); if (!P) return; document.querySelectorAll('.align-ping').forEach(x => x.remove());
    const d = document.createElement('div'); d.className = 'align-ping'; d.style.left = P.x + 'px'; d.style.top = P.y + 'px'; document.body.appendChild(d); setTimeout(() => d.remove(), 3500);
  }
  // v7.8 : langue de la bande du haut en ce moment (l'info qui défile, sinon la phrase d'accueil au milieu de la bande)
  function langueBande() {
    try { if (bande.classList.contains('on')) return flash.classList.contains('en') ? 'en' : 'fr';
      const b = bande.getBoundingClientRect(), cx = b.left + b.width * 0.35;
      for (const sp of piste.children) { const q = sp.getBoundingClientRect(); if (q.left <= cx && q.right >= cx) return sp.classList.contains('en') ? 'en' : 'fr'; } } catch (e) {}
    return 'fr';
  }
  // v9.3 (demande d'Adel) : « LE GRAPH BALANCE » pas clair → titres drôles et liés au marché, qui changent à chaque bulle (jamais de sens ni de prix)
  const TITRES_PUNCH = [
    ['🕵️ LE GRAPHIQUE A REPÉRÉ UN TRUC', '🕵️ THE CHART SPOTTED SOMETHING'],
    ['🐋 LES BALEINES SE RÉVEILLENT', '🐋 THE WHALES ARE WAKING UP'],
    ['🍿 SORS LE POP-CORN, LE MARCHÉ JOUE', '🍿 GRAB THE POPCORN, THE MARKET IS ON'],
    ['🕯️ LES BOUGIES ONT UN TRUC À TE DIRE', '🕯️ THE CANDLES HAVE SOMETHING TO SAY'],
    ['☕ PAUSE CAFÉ ? PAS POUR LE MARCHÉ', '☕ COFFEE BREAK? NOT FOR THE MARKET'],
    ['🎢 ACCROCHE TA CEINTURE', '🎢 FASTEN YOUR SEATBELT'],
    ['📢 FLASH DU MARCHÉ', '📢 MARKET FLASH'],
    ['🧲 LE PRIX CHERCHE LA LIQUIDITÉ', '🧲 PRICE IS HUNTING LIQUIDITY'],
  ];
  let titreN = 0;
  function coeurs(n, liste, sensForce) {
    try {
      const cle = (liste || []).join(''), g = PUNCH.find(x => x[0].test(cle)) || PUNCH[PUNCH.length - 1];
      const [fr, en] = g[1 + (punchN++ % (g.length - 1))], tok = ++punchTok;
      const e = document.createElement('div'); e.className = 'align-punch';
      if (g === PUNCH[PUNCH.length - 1] || /😊|😏|⏰|👆|🙏|💬|📢/.test(cle)) e.dataset.bas = '1';   // v8.1 : pastille de motivation → en bas vers le tableau de bord
      // v7.8 (demande d'Adel) : la pastille parle la MÊME langue que la bande du haut (FR avec FR, EN avec EN) pour éviter les confusions
      const parts = (txt, defEmo) => { const m = txt.split(' '); const em = /^\p{Extended_Pictographic}/u.test(m[0]) ? m.shift() : defEmo; return [em, m.join(' ')]; };
      const [emoFr, txtFr] = parts(fr, '💬'), [emoEn, txtEn] = parts(en, emoFr);
      let lgCour = null; titreN++;
      const affiche = lg => { lgCour = lg; e.classList.toggle('en', lg === 'en'); const [em, tx] = lg === 'en' ? [emoEn, txtEn] : [emoFr, txtFr];
        e.innerHTML = '<span class="qui">' + TITRES_PUNCH[titreN % TITRES_PUNCH.length][lg === 'en' ? 1 : 0] + '</span><span class="emo">' + esc(em) + '</span> <span class="txt">' + esc(tx) + '</span>';
        e.style.animation = 'none'; void e.offsetWidth; e.style.animation = ''; };
      document.querySelectorAll('.align-punch').forEach(x => x.remove());
      affiche(langueBande()); document.body.appendChild(e);
      const sensP = sensForce || sensPastille(cle); placerPastille(e, sensP); ping();
      const debut = Date.now(), veille = setInterval(() => { try {
        if (tok !== punchTok || Date.now() - debut > 16000) { clearInterval(veille); e.remove(); return; }
        const lg = langueBande(); if (lg !== lgCour) { affiche(lg); placerPastille(e, sensP); } } catch (er) { clearInterval(veille); } }, 700);
    } catch (e) {}
  }
  function choisirPlateforme(v) { PLATEFORME = v; try { localStorage.setItem('alignPlateforme', v); } catch (e) {} remplir(); }
  // v6.7 : marché ennuyant → une grosse tête qui bâille traverse l'écran (😴 ↔ 🥱), puis des cœurs
  const cssEnnui = document.createElement('style');
  cssEnnui.textContent = `#align-ennui{position:fixed;z-index:10002;pointer-events:none;font-size:120px;animation:ennuiPasse 6s ease-in-out forwards}
  @keyframes ennuiPasse{0%{transform:translateX(0) rotate(-8deg);opacity:0}10%{opacity:1}50%{transform:translateX(var(--w)) rotate(8deg) scale(1.15)}
    90%{opacity:1}100%{transform:translateX(calc(var(--w) * 2)) rotate(-8deg);opacity:0}}`;
  document.head.appendChild(cssEnnui);
  function teteEnnui() {
    try {
      const r = zoneGraphique(), e = document.createElement('div'); e.id = 'align-ennui'; e.textContent = '🥱';
      e.style.left = (r.left + 20) + 'px'; e.style.top = (r.top + (r.height || 700) * 0.35) + 'px';
      e.style.setProperty('--w', ((r.width - 260) / 2) + 'px');
      document.getElementById('align-ennui')?.remove(); document.body.appendChild(e);
      let n = 0; const t = setInterval(() => { e.textContent = (++n % 2) ? '😴' : '🥱'; }, 700);
      setTimeout(() => { clearInterval(t); e.remove(); coeurs(10, ['❤️', '👆', '💜']); }, 6000);
    } catch (e) {}
  }
  window.__ALIGN_SHOW__ = { ennui: teteEnnui, pop, lueur, coeurs, lignes: () => lignesAlign() };
  // une info du spectacle sur la bande : jamais par-dessus une vraie info du bot, et pas plus d'une par minute
  let dernierShow = 0;
  function bandeShow(txt, source) {
    if (occupe || file.length || Date.now() - dernierShow < 52000) return false;
    dernierShow = Date.now(); montrer(txt, false, 1, undefined, false, source); return true;
  }
  // v5.9 : chaque événement vu à l'écran part aussi au bot → message détaillé dans la chaîne Telegram du marché
  function codeMarche() { const s = String((chart() && chart().symbol()) || ''); return /BTC/i.test(s) ? 'BTC' : /XAU|GOLD/i.test(s) ? 'GOLD' : ''; }
  function versBot(typ, d, minutes, ligne) {
    const mk = codeMarche(); if (!mk) return;
    envoyerEcran(['EVT', mk, typ, d, minutes || '', ligne || ''].join('|'));
  }
  // v6.2 : les lignes ALIGN du graphique (ENTRÉE, SL, TP1, TP2) lues directement dans l'indicateur
  function lignesAlign() {
    const res = {};
    try {
      const mod = chart()._chartWidget.model().model();
      for (const ds of mod.dataSources()) {
        if (!/ALIGN/.test(String(ds.title && ds.title()))) continue;
        const vu = new Set();
        (function walk(o, d, dansData) {
          if (!o || d > 8 || typeof o !== 'object' || vu.has(o)) return; vu.add(o);
          if (o instanceof Map) { o.forEach(v => walk(v, d + 1, dansData)); return; }
          if (dansData && typeof o.t === 'string' && typeof o.y === 'number') {
            const n = (o.t.match(/^\s*(ENTRÉE|SL|TP1|TP2)\b/) || [])[1];
            if (n && (!res[n] || o.id > res[n].id)) res[n] = { id: o.id, y: o.y, tt: o.tt || o.t };
            return;
          }
          for (const k of Object.keys(o)) walk(o[k], d + 1, dansData || k === '_primitivesDataById');
        })(ds.graphics()._primitivesCollection.dwglabels, 0, false);
      }
    } catch (e) {}
    return res;
  }

  // v7.5 (demande d'Adel) : les ZONES de l'indicateur (FVG, ORDER BLOCK) lues dans le graphique
  function zonesAlign() {
    const res = [];
    try {
      const mod = chart()._chartWidget.model().model();
      for (const ds of mod.dataSources()) {
        if (!/ALIGN/.test(String(ds.title && ds.title()))) continue;
        const vu = new Set();
        (function walk(o, d, dansData) {
          if (!o || d > 8 || typeof o !== 'object' || vu.has(o)) return; vu.add(o);
          if (o instanceof Map) { o.forEach(v => walk(v, d + 1, dansData)); return; }
          if (dansData && typeof o.y1 === 'number' && typeof o.y2 === 'number') { if (o.t) res.push({ id: o.id, t: String(o.t), hi: Math.max(o.y1, o.y2), lo: Math.min(o.y1, o.y2) }); return; }
          for (const k of Object.keys(o)) walk(o[k], d + 1, dansData || k === '_primitivesDataById');
        })(ds.graphics()._primitivesCollection.dwgboxes, 0, false);
      }
    } catch (e) {}
    return res;
  }
  function infosAlign() {   // v7.6 : les marqueurs ⓘ de l'indicateur (le plus récent de chaque sorte)
    const res = {};
    try { const mod = chart()._chartWidget.model().model();
      for (const ds of mod.dataSources()) { if (!/ALIGN/.test(String(ds.title && ds.title()))) continue; const vu = new Set();
        (function walk(o, d, dansData) { if (!o || d > 8 || typeof o !== 'object' || vu.has(o)) return; vu.add(o);
          if (o instanceof Map) { o.forEach(v => walk(v, d + 1, dansData)); return; }
          if (dansData && typeof o.t === 'string' && typeof o.y === 'number') { const e = (o.t.match(/^(✂️|↩️|✅)\s*ⓘ/) || [])[1]; if (e && (!res[e] || o.id > res[e].id)) res[e] = { e, id: o.id, y: o.y }; return; }
          for (const k of Object.keys(o)) walk(o[k], d + 1, dansData || k === '_primitivesDataById');
        })(ds.graphics()._primitivesCollection.dwglabels, 0, false); } } catch (e) {}
    return Object.values(res);
  }
  function texteZone(t, m) {
    const consommation = (String(t).match(/(\d{1,3})\s*%\s*(?:consommée|consommé)/i) || [])[1];
    const etat = consommation == null ? '' : ' • ' + consommation + '% de zone consommée';
    return /FVG/i.test(t) ? '🧲 ' + m + ' • ZONE FVG' + etat + ' : le marché est en train de combler ce déséquilibre 👀 rebond ou cassure ? 📲 en temps réel : lien en bio 🎁'
      : /ORDER|OB\b/i.test(t) ? '🏦 ' + m + ' • ORDER BLOCK' + etat + ' : la zone institutionnelle est en cours de mitigation 👀 📲 en temps réel : lien en bio 🎁'
      : '👀 ' + m + ' • ' + String(t).toUpperCase() + ' : zone clé du marché • ce qu\'elle annonce : 📲 lien en bio 🎁';
  }
  // prix sous le doigt / la souris (coordonnées de la page → prix du graphique)
  function prixA(yPage) {
    try { const r = zoneGraphique(), ser = chart()._chartWidget.model().mainSeries(), ps = ser.priceScale(), fv = ser.firstValue();
      const p = ps.coordinateToPrice(yPage - r.top, fv), p2 = ps.coordinateToPrice(yPage - r.top + 12, fv); return { p, tol: Math.abs(p - p2) }; } catch (e) { return null; }
  }
  // v7.5 : clic / tap (ou souris posée) sur une ligne ALIGN ou une zone → l'explication défile TOUT DE SUITE dans la bande + pastille
  const vuClic = {};
  function expliquerSous(xPage, yPage, clic) {
    const r = zoneGraphique(); if (xPage < r.left || xPage > r.left + r.width - 70 || yPage < r.top + 86 || yPage > r.top + (r.height || 600)) return false;
    const q = prixA(yPage); if (!q || !isFinite(q.p)) return false;
    const m = nomMarche(), LG = lignesAlign(); let cle = null, txt = null, coul = 'alerte', emo = '👀';
    for (const n of ['ENTRÉE', 'SL', 'TP1', 'TP2']) { const l = LG[n]; if (l && Math.abs(l.y - q.p) <= q.tol) { cle = 'l' + n + Math.round(l.y); txt = teaserLigne(n); coul = couleurLigne(n); emo = n.startsWith('TP') ? '🎯' : n === 'SL' ? '🧱' : '🔮'; break; } }
    // v7.6 (demande d'Adel) : les petits ⓘ du graphique (✂️ trait de décision, ↩️ retournement, ✅ confirmation) sont expliqués aussi
    if (!cle) for (const o of infosAlign()) { if (Math.abs(o.y - q.p) <= q.tol * 1.5) { cle = 'i' + o.e + Math.round(o.y); emo = o.e === '↩️' ? '🔄' : o.e === '✂️' ? '🧱' : '🔮';
      txt = o.e === '✂️' ? '✂️ ' + m + ' • TRAIT BLANC = LIGNE DE DÉCISION : c\'est la clôture 15 min de l\'autre côté qui décide du sens 👀 • une mèche ne compte pas • 📲 lien en bio 🎁'
        : o.e === '↩️' ? '↩️ ' + m + ' • LIGNE DE RETOURNEMENT : si une bougie 15 min clôture de l\'autre côté, le plan s\'inverse 🔄 • le coach te prévient • 📲 lien en bio 🎁'
        : '✅ ' + m + ' • CONFIRMATION : les petites unités doivent aller dans le même sens avant d\'entrer 👀 • 📲 lien en bio 🎁'; break; } }
    if (!cle) for (const z of zonesAlign()) { if (q.p <= z.hi + q.tol / 2 && q.p >= z.lo - q.tol / 2) { cle = 'z' + z.id; txt = texteZone(z.t, m); emo = /FVG/i.test(z.t) ? '🧲' : /ORDER/i.test(z.t) ? '🏦' : '👀'; break; } }
    if (!cle) return false;
    const now = Date.now(); window.__alignExpl = now; if (now - (vuClic[cle] || 0) < (clic ? 4000 : 45000)) return true; vuClic[cle] = now;
    montrer(txt, false, 1, coul, true); coeurs(1, [emo]); lueur(0);   // pastille : en haut si le marché baisse, en bas s'il monte
    return true;
  }
  let posDown = null, survolT = null, vivant = true;   // v7.7 : une ancienne bande arrêtée ne réagit plus aux clics (plus de pastilles en double)
  document.addEventListener('pointerdown', e => { posDown = { x: e.clientX, y: e.clientY, t: Date.now() }; }, { passive: true, capture: true });
  document.addEventListener('pointerup', e => { try { if (!vivant) return;
    if (!posDown || Math.hypot(e.clientX - posDown.x, e.clientY - posDown.y) > 8 || Date.now() - posDown.t > 700) return;   // un glisser n'est pas un clic
    if (e.target && e.target.closest && e.target.closest('.chart-markup-table')) expliquerSous(e.clientX, e.clientY, true);
  } catch (er) {} }, { passive: true, capture: true });
  document.addEventListener('pointermove', e => { if (!vivant || e.pointerType !== 'mouse') return; clearTimeout(survolT); const x0 = e.clientX, y0 = e.clientY;
    survolT = setTimeout(() => { try { expliquerSous(x0, y0, false); } catch (er) {} }, 600); }, { passive: true, capture: true });   // souris posée 0,6 s sur ENTRÉE / SL / TP ou une zone
  const deja = {};
  function uneFois(cle) { if (deja[cle]) return false; deja[cle] = 1; return true; }
  const PHRASES = {
        casseBas: [['🚨', 'ÇA CASSE !', ' casse le dernier plus bas 📉 • ça peut couler encore… infos en temps réel : lien en bio 🎁']],
    casseHaut: [['🚀', 'ÇA CASSE !', ' casse le dernier plus haut 📈 • ça peut décoller… infos en temps réel : lien en bio 🎁']],
    volume: [['🐋', 'LES BALEINES BOUGENT', ' : gros volume 👀 quelque chose se prépare • lien en bio 🎁']],
    hausse: ['📈 {m} veut remonter… jusqu\'où ? le coach le sait : lien en bio 🎁',
             '🟢 {m} reprend des forces 💪 le marché pourrait remonter • plus d\'infos : lien en bio 🎁',
             '🚀 Les acheteurs reviennent sur {m} 👀 la suite en temps réel : lien en bio 🎁'],
    baisse: ['📉 {m} sous pression… va-t-il couler ? réponse en temps réel : lien en bio 🎁',
             '🔴 Les vendeurs tiennent {m} 😬 ça peut encore descendre • plus d\'infos : lien en bio 🎁',
             '🌊 {m} glisse… le coach surveille chaque bougie : lien en bio 🎁'],
    // v6.1 : où est le prix (sans le donner) + le lien en bio = être BRANCHÉ au marché
    bas_zone: ['📍 {m} est posé sur une zone clé en bas 👀 rebond ou cassure ? 📲 connecte-toi au marché depuis ton portable : lien en bio 🎁',
               '🧲 {m} teste le bas de sa zone… les acheteurs vont-ils tenir ? 📡 en direct : lien en bio 🎁'],
    haut_zone: ['📍 {m} touche le haut de sa zone 👀 cassure ou rejet ? 📲 connecte-toi au marché depuis ton portable : lien en bio 🎁',
                '🧱 {m} bute sous un plafond… les vendeurs vont-ils frapper ? 📡 en direct : lien en bio 🎁'],
    milieu: ['🧭 {m} au milieu de sa zone : il cherche sa direction… le coach te dit quand ça part 📡 lien en bio 🎁',
             '⚖️ {m} en équilibre : acheteurs et vendeurs se regardent… qui va craquer ? 👀 lien en bio 🎁'],
    branche: ['📲 Ton portable connecté au marché en temps réel : chaque bougie expliquée en direct • lien en bio 🎁',
              '📡 Connecté au marché depuis ton portable : le coach lit chaque bougie avec toi • lien en bio 🎁',
              '🧠 Tu vois les bougies, le coach te dit ce qu\'elles préparent • lien en bio 🎁',
              '⚡ Ressens le marché en direct : pression, pièges, accélérations… tout est dans le lien en bio 🎁'],
    // v6.5 : marché tout calme → on parle comme un pote, selon l'heure
    calme_matin: ['☕ {m} est tout calme… va te faire un café tranquille, on te prévient quand ça bouge 📲 lien en bio 🎁',
                  '🥐 Petit-déj time : {m} se réveille doucement… le coach veille pour toi • lien en bio 🎁'],
    calme_midi: ['🍔 {m} fait la sieste… va manger un bout, le coach surveille pour toi 👀 lien en bio 🎁',
                 '🥗 Pause déj : {m} bouge pas d\'un poil… on te ping dès que ça part • lien en bio 🎁'],
    calme_aprem: ['🧃 {m} chill grave… prends une pause, le marché te fera signe 😎 lien en bio 🎁',
                  '☕ Café de l\'aprèm ? {m} est en mode tranquille… le coach reste connecté • lien en bio 🎁'],
    calme_soir: ['🍕 {m} est calme ce soir… va dîner, le coach garde un œil 👀 lien en bio 🎁',
                 '🎮 Soirée chill : {m} ne fait rien de fou… on te prévient si ça s\'énerve • lien en bio 🎁'],
    calme_nuit: ['😴 Il est tard et {m} dort à moitié… va te reposer, le coach veille 🌙 lien en bio 🎁',
                 '🌙 {m} roupille… recharge les batteries, le marché sera encore là demain 💤 lien en bio 🎁'],
    // v7.7 (demande d'Adel) : marché calme = on taquine poliment, style jeune
    ennui: ['👀 Au lieu de regarder sans rien faire… le marché n\'a pas encore de point d\'entrée 😅 tapote l\'écran pour le réveiller 👆 • lien en bio 🎁',
            '😎 Pas d\'entrée pour l\'instant : la team patiente… toi tu tapotes, nous on surveille 😉 • lien en bio 🎁',
            '🥱 Pfff… on s\'ennuie, {m} est trop calme 😴 pense à tapoter l\'écran ❤️ et à t\'abonner • lien en bio 🎁',
            '😴 Marché ennuyant sur {m}… allez, tapote l\'écran pour le réveiller 👆❤️ et abonne-toi • lien en bio 🎁'],
    // v8.0 (demande d'Adel) : on pousse les gens à commenter, avec des vannes différentes
    commente: ['💬 À toi de jouer : {m} va MONTER 📈 ou DESCENDRE 📉 ? Écris-le en commentaire, on verra qui a raison 😏 • lien en bio 🎁',
               '📝 Sondage express : {m} ⬆️ ou ⬇️ dans 15 min ? Commente « haut » ou « bas » 👇 • lien en bio 🎁',
               '🧠 Les meilleurs pronostics en commentaire… {m} continue ou retrace ? Montre que t\'as le flair 😎 • lien en bio 🎁',
               '😂 Celui qui devine la prochaine bougie de {m} gagne… notre respect éternel 🙏 commente ! • lien en bio 🎁'],
    range: ['😴 {m} se compresse… avant le gros mouvement ? ⚡ tiens-toi prêt • lien en bio 🎁',
            '🧲 {m} hésite… la prochaine clôture peut tout décider ⏱ lien en bio 🎁']
  };
  // Commentaire factuel du graphique : tendance de fond, respiration récente, compression et volume.
  // Aucun prix ni niveau n'est prononcé ; la voix et la bande racontent la même lecture.
  function commentaireMarcheEnDirect(B, moyR, moyV, m) {
    if (!Array.isArray(B) || B.length < 25) return null;
    const c = B.slice(-12).map(x => Number(x[4]));
    const fond = c[c.length - 1] - c[0];
    const recent = c[c.length - 1] - c[c.length - 4];
    const seuil = Math.max(moyR * 0.35, 1e-9);
    const dFond = Math.abs(fond) <= seuil ? 0 : Math.sign(fond);
    const dRecent = Math.abs(recent) <= seuil * 0.45 ? 0 : Math.sign(recent);
    const rangeRecent = B.slice(-4).reduce((a, x) => a + Math.max(0, x[2] - x[3]), 0) / 4;
    const rangeAvant = B.slice(-20, -4).reduce((a, x) => a + Math.max(0, x[2] - x[3]), 0) / 16;
    const hh = Math.max(...B.slice(-20).map(x => x[2]));
    const ll = Math.min(...B.slice(-20).map(x => x[3]));
    const pos = (B[B.length - 1][4] - ll) / Math.max(hh - ll, 1e-9);
    const volume = B[B.length - 1][5] || 0;
    const volumeFort = moyV > 0 && volume >= 1.8 * moyV;
    // Bougie en cours (anticipation provisoire) : définie ici, car cette fonction ne recevait que B.
    const cur = B[B.length - 1], prev = B.slice(-21, -1);
    const niveauBas = Math.min(...prev.map(x => x[3]));
    const niveauHaut = Math.max(...prev.map(x => x[2]));
    const corpsAbs = Math.abs(cur[4] - cur[1]);
    const mecheBasse = Math.min(cur[1], cur[4]) - cur[3];
    const mecheHaute = cur[2] - Math.max(cur[1], cur[4]);
    const seuilSweep = Math.max(moyR * 0.05, 1e-9);
    // Le graphique peut montrer une chasse en cours avant la clôture : on la décrit comme provisoire, jamais comme un signal.
    const chasseSousSupport = cur[3] < niveauBas - seuilSweep && cur[4] > niveauBas && cur[4] > cur[1]
      && mecheBasse >= Math.max(corpsAbs * 0.8, moyR * 0.08);
    const chasseAuDessus = cur[2] > niveauHaut + seuilSweep && cur[4] < niveauHaut && cur[4] < cur[1]
      && mecheHaute >= Math.max(corpsAbs * 0.8, moyR * 0.08);
    // Bougie clôturée (validation) : balayage puis réintégration confirmés sur la dernière bougie terminée.
    // C'est un indice de rejet, jamais une autorisation d'entrée à lui seul (confirmation M5/M15/H1/H4 requise).
    const terminee = B[B.length - 2], avant = B.slice(-22, -2);
    const ancienBas = Math.min(...avant.map(x => Number(x[3])));
    const ancienHaut = Math.max(...avant.map(x => Number(x[2])));
    const corpsT = Math.abs(Number(terminee[4]) - Number(terminee[1]));
    const mecheBasseT = Math.min(Number(terminee[1]), Number(terminee[4])) - Number(terminee[3]);
    const mecheHauteT = Number(terminee[2]) - Math.max(Number(terminee[1]), Number(terminee[4]));
    const balayageBas = Number(terminee[3]) < ancienBas - seuil * 0.08 &&
      Number(terminee[4]) > ancienBas && Number(terminee[4]) >= Number(terminee[1]) &&
      mecheBasseT >= Math.max(corpsT * 1.1, seuil * 0.12);
    const balayageHaut = Number(terminee[2]) > ancienHaut + seuil * 0.08 &&
      Number(terminee[4]) < ancienHaut && Number(terminee[4]) <= Number(terminee[1]) &&
      mecheHauteT >= Math.max(corpsT * 1.1, seuil * 0.12);
    // Priorité : validation clôturée > anticipation en cours > tendance.
    let lecture;
    if (balayageBas) lecture = 'La dernière bougie clôturée est passée sous un ancien creux puis a réintégré la zone avec un rejet acheteur. Possible chasse de liquidité vendeuse ; ce n’est pas encore un signal LONG, on attend la confirmation M5, M15, H1 et H4.';
    else if (balayageHaut) lecture = 'La dernière bougie clôturée est passée au-dessus d’un ancien sommet puis a réintégré la zone avec un rejet vendeur. Possible chasse de liquidité acheteuse ; ce n’est pas encore un signal SHORT, on attend la confirmation M5, M15, H1 et H4.';
    else if (chasseSousSupport) lecture = 'Possible chasse de liquidité sous un support : le prix repasse au-dessus et les acheteurs réagissent. La bougie est encore en formation ; seule sa clôture dira si le piège est confirmé.';
    else if (chasseAuDessus) lecture = 'Possible chasse de liquidité au-dessus d’une résistance : le prix repasse dessous et les vendeurs réagissent. La bougie est encore en formation ; seule sa clôture dira si le piège est confirmé.';
    else if (dFond > 0 && dRecent < 0) lecture = 'La tendance récente reste orientée à la hausse, mais les dernières bougies corrigent. Les acheteurs doivent défendre leur mouvement ; on attend une clôture avant de conclure.';
    else if (dFond < 0 && dRecent > 0) lecture = 'Le mouvement de fond reste orienté à la baisse, mais le marché tente un rebond. Les vendeurs doivent encore montrer s’ils gardent la main ; aucune anticipation.';
    else if (dFond > 0 && dRecent >= 0) lecture = 'Les acheteurs gardent l’avantage sur les dernières bougies. Je surveille si l’impulsion se prolonge ou si le marché commence à souffler.';
    else if (dFond < 0 && dRecent <= 0) lecture = 'Les vendeurs gardent la pression sur les dernières bougies. Je surveille si la baisse continue ou si les acheteurs commencent à réagir.';
    else if (rangeAvant > 0 && rangeRecent < 0.65 * rangeAvant) lecture = 'Le marché se resserre : les bougies perdent de l’amplitude et les deux camps attendent. La prochaine clôture aidera à départager acheteurs et vendeurs.';
    else lecture = 'Le marché évolue en range : acheteurs et vendeurs se neutralisent pour le moment. Je surveille une sortie confirmée plutôt que de deviner le prochain mouvement.';
    if (pos > 0.85) lecture += ' Le prix travaille le haut de sa zone récente : attention à une réaction ou à une cassure confirmée.';
    else if (pos < 0.15) lecture += ' Le prix travaille le bas de sa zone récente : attention à une réaction ou à une cassure confirmée.';
    if (volumeFort) lecture += ' Le volume est nettement supérieur à sa moyenne récente.';
    return '🎙 ' + m + ' : ' + lecture;
  }
  let tendN = 0, derniereTend = Date.now(), derniereCoach = 0, arme = null;   // horloges séparées : l'animateur ne bloque plus le commentaire du marché
  function regarder() {
    try {
      if (arme && !botAConfirme()) arme = null;             // v12.2.8 : pas de « grosse distribution / accumulation » sans confirmation du bot
      if (retour) return;                                   // un abonné a la main : on ne parle pas par-dessus
      const B = barres(40); if (B.length < 25) return;
      const cur = B[B.length - 1], prev = B.slice(-21, -1), m = nomMarche();
      const moyR = prev.reduce((a, x) => a + (x[2] - x[3]), 0) / prev.length || 1;
      const moyV = prev.reduce((a, x) => a + (x[5] || 0), 0) / prev.length || 0;
      const corps = cur[4] - cur[1], sens = corps < 0 ? -1 : 1, id = m + cur[0];
      // v7.5 (constat d'Adel : « il dit que ça va chuter et le marché explose ») : une annonce contredite par le marché est ANNULÉE tout de suite
      if (arme && (cur[4] - arme.p) * arme.d < -0.6 * (arme.r || moyR)) {
        const d = -arme.d, am = arme.m; arme = null;
        montrer('🔄 CHANGEMENT DE PROGRAMME sur ' + am + ' : le marché a changé d\'avis ' + (d === 1 ? '📈' : '📉') + ' • on suit le marché, on ne le combat pas 💪 • la suite en temps réel : lien en bio 🎁', false, 1, d === 1 ? 'haut' : 'bas', true);
        lueur(d); setTimeout(() => coeurs(1, ['🔄'], d), 1500);
        return;
      }
      const pente40 = (cur[4] - B[0][4]) / moyR;   // v7.5 : la tendance de fond (40 bougies) doit être d'accord avant d'annoncer un sens
      // 0) v6.2 : le prix arrive sur une ligne ALIGN → son explication défile dans la bande (2 fois), une fois par quart d'heure
      const LG = lignesAlign(), q15 = Math.floor(Date.now() / 900000);
      for (const n of ['TP2', 'TP1', 'SL', 'ENTRÉE']) {
        const l = LG[n]; if (!l) continue;
        const traverse = B.length > 1 && (B[B.length - 2][4] - l.y) * (cur[4] - l.y) < 0;   // v7.4 : la ligne est traversée d'un coup
        if ((Math.abs(cur[4] - l.y) < 0.3 * moyR || traverse) && uneFois('ligne' + m + n + Math.round(l.y) + q15)) {
          const tete = '👀 ' + m + ' arrive sur une zone clé';
          montrer(tete + ' • le marché prépare quelque chose 👀 pourquoi ? 📲 lien en bio 🎁', false, 2, couleurLigne(n));
          versBot('ligne', cur[4] > l.y ? 1 : -1, '', n);
          setTimeout(() => coeurs(1, ['🤔']), 3600);   // v7.0 : « rentrer ou couper ? » + lien en bio
          if (n.startsWith('TP') && !botDedans(m)) { montrer('👀 ' + m + ' a touché l\'objectif du graphique • pas de position du coach cette fois ⏳ • attends le prochain cycle : lien en bio', false, 1); }
        else if (n.startsWith('TP')) { explosionArgent(cur[4] > l.y ? -1 : 1); feuArtifice(traverse ? '🎯 OBJECTIF ATTEINT D\'UN COUP !' : '🍾 ÇA ENCAISSE !'); pluieBillets(35); setTimeout(() => coeurs(1, ['💥']), 2500); }   // v7.4 : ligne bleue touchée = champagne + billets + explosion   // v7.4 : TP traversé d'un coup = explosion   // objectif atteint : l'argent suit le sens du marché
          return;
        }
      }
      // 0b) v7.5 : le prix entre dans une zone FVG / ORDER BLOCK → explication dans la bande + pastille (une fois par quart d'heure)
      for (const z of zonesAlign()) {
        const dedans = cur[4] <= z.hi && cur[4] >= z.lo, avant = B[B.length - 2][4] > z.hi || B[B.length - 2][4] < z.lo;
        if (dedans && avant && uneFois('zone' + z.id + q15)) { montrer(texteZone(z.t, m), false, 1, 'alerte'); coeurs(1, [/FVG/i.test(z.t) ? '🧲' : '🏦'], cur[4] > B[B.length - 2][4] ? 1 : -1); lueur(0); versBot('ligne', cur[4] > B[B.length - 2][4] ? 1 : -1, '', /FVG/i.test(z.t) ? 'FVG' : 'OB'); return; }
      }
      // 0c) v8.0 (demande d'Adel) : le prix touche son dernier plus haut / plus bas alors que le plan attend ailleurs → on taquine + on fait commenter
      { const hh0 = Math.max(...prev.map(x => x[2])), ll0 = Math.min(...prev.map(x => x[3])), versHaut = (hh0 - cur[4]) < 0.4 * moyR, versBas = (cur[4] - ll0) < 0.4 * moyR;
        if (LG['ENTRÉE'] && (versHaut || versBas) && uneFois('tente' + m + q15)) {
          montrer('🤔 ' + m + (versHaut ? ' touche son dernier plus haut' : ' touche son dernier plus bas') + '… t\'as envie de rentrer là ? 😏 Ça continue ou ça retrace ? 💬 dis-le en commentaire • le scénario complet est déjà prêt : lien en bio 🎁', false, 1, 'alerte');
          setTimeout(() => coeurs(1, ['💬'], versHaut ? 1 : -1), 1500); return; } }
      // 1) bougie qui accélère (corps > 1,6× la taille moyenne) : explosion visuelle + lueur rouge/verte
      if (Math.abs(corps) > 1.6 * moyR && uneFois('acc' + id)) {
        pop(sens === -1 ? '📉' : '📈', 'ÇA ACCÉLÈRE ' + (sens === -1 ? '🔴 ' : '🟢 ') + m, sens, 'jusqu\'où ? la suite en temps réel : lien en bio 🎁'); lueur(sens); versBot('acc', sens); setTimeout(() => coeurs(1, ['⏰']), 3600);
        return;
      }
      // 2) cassure du dernier plus haut / plus bas (20 bougies) : on le montre sans donner le prix
      const hh = Math.max(...prev.map(x => x[2])), ll = Math.min(...prev.map(x => x[3]));
      if (cur[4] < ll && uneFois('cb' + id)) { pop('🚨', 'ÇA CASSE 🔴 ' + m, -1, 'dernier plus bas cassé 📉 ça peut couler encore… infos en temps réel : lien en bio 🎁'); lueur(-1); versBot('casse', -1); setTimeout(() => coeurs(1, ['⏰']), 3600); return; }
      if (cur[4] > hh && uneFois('ch' + id)) { pop('🚀', 'ÇA CASSE 🟢 ' + m, 1, 'dernier plus haut cassé 📈 ça peut décoller… infos en temps réel : lien en bio 🎁'); lueur(1); versBot('casse', 1); setTimeout(() => coeurs(1, ['⏰']), 3600); return; }
      // 3) gros volume
      if (moyV > 0 && (cur[5] || 0) > 2.5 * moyV && uneFois('vol' + id)) { pop('🐋', 'LES BALEINES BOUGENT sur ' + m, 0, 'gros volume 👀 quelque chose se prépare • lien en bio 🎁'); coeurs(8, ['🐋', '💰', '👀']); versBot('volume', sens); return; }
      // 5) v5.6 ANTICIPATION (demande d'Adel) : dire AVANT que ça accélère, avec le chrono jusqu'à la clôture 15 min
      //    pression = tendance nette + bougies qui se compressent ou prix collé au dernier plus bas/haut (la mèche va transpercer)
      const c10b = B.slice(-10).map(x => x[4]), pente10 = (c10b[9] - c10b[0]) / moyR;
      const dirT = pente10 > 0.8 ? 1 : pente10 < -0.8 ? -1 : 0;
      const comp = B.slice(-4).reduce((a, x) => a + (x[2] - x[3]), 0) / 4 < 0.75 * moyR;
      const colle = dirT === -1 ? (cur[4] - ll) < 0.6 * moyR : dirT === 1 ? (hh - cur[4]) < 0.6 * moyR : false;
      const quart = Math.floor(Date.now() / 900000), minRest = Math.max(1, Math.ceil((900 - Math.floor(Date.now() / 1000) % 900) / 60));
      const daccord = dirT && Math.sign(pente40) === dirT && Math.abs(pente40) > 1.5 && corps * dirT > -0.5 * moyR;   // v7.5 : jamais contre la tendance de fond ni contre la bougie en cours
      if (daccord && (comp || colle) && uneFois('pr' + m + quart)) {
        arme = { d: dirT, quart, m, p: cur[4], r: moyR };
        lueur(dirT); coeurs(8, dirT === -1 ? ['📉', '🌊', '⚡'] : ['📈', '🚀', '⚡']);
        pop('⏳', 'COMPTE À REBOURS sur ' + m + ' : ' + (dirT === -1 ? '🔴 GROSSE DISTRIBUTION' : '🟢 GROSSE ACCUMULATION'), dirT,
            'dans ' + minRest + ' min max ⏳ la team : abonne-toi, partage • lien en bio 🎁');
        versBot('pression', dirT, minRest); setTimeout(() => coeurs(1, ['📢'], dirT), 9000);   // v7.6 : « annonce à venir » en pastille, après la punchline
        return;
      }
      // 5b) v6.9 FEINTE : 3 bougies qui repartent contre la tendance → « beaucoup vont y laisser des plumes »
      const c3 = B.slice(-4).map(x => x[4]), contre = dirT ? (c3[3] - c3[0]) * -dirT / moyR : 0;
      if (dirT && contre > 1.0 && uneFois('fe' + m + quart)) {
        const PF = dirT === -1
          ? ['🪤 ATTENTION LA FEINTE sur ' + m + ' : le marché fait semblant de remonter… beaucoup vont acheter trop tôt et y laisser des plumes 🪶 • lien en bio 🎁',
             '🎣 ' + m + ' remonte… qui va mordre à l\'hameçon ? les gros adorent ce genre de piège 😏 • Ne te fais pas piéger : lien en bio 🎁']
          : ['🪤 ATTENTION LA FEINTE sur ' + m + ' : le marché fait semblant de chuter… beaucoup vont vendre trop tôt et y laisser des plumes 🪶 • lien en bio 🎁',
             '🎣 ' + m + ' recule… qui va mordre à l\'hameçon ? les gros adorent ce genre de piège 😏 • ne cours pas après la bougie : lien en bio 🎁'];
        montrer(PF[quart % 2], false, 2, 'alerte'); lueur(0); coeurs(8, ['🪤', '🎣', '🪶']);
        versBot('feinte', dirT, minRest);
        return;
      }
      // 6) manipulation : grosse mèche CONTRE la tendance (les gros piègent) → la vraie direction peut arriver
      const meche = dirT === -1 ? cur[2] - Math.max(cur[1], cur[4]) : dirT === 1 ? Math.min(cur[1], cur[4]) - cur[3] : 0;
      if (daccord && meche > 1.1 * moyR && uneFois('mn' + id)) {
        arme = { d: dirT, quart, m, p: cur[4], r: moyR };
        lueur(dirT);
        pop('🌀', 'MANIPULATION sur ' + m, dirT, (dirT === -1 ? 'les gros piègent les acheteurs… la belle distribution 📉' : 'les gros piègent les vendeurs… le rechargement 📈')
            + ' dans ' + minRest + ' min max ⏳ • abonne-toi, partage • lien en bio 🎁');
        versBot('manip', dirT, minRest);
        return;
      }
      // 4) toutes les ~7 min : la bande dit où le marché a l'air d'aller (sans prix) et renvoie vers le lien en bio
      // v6.1 : marché calme = on parle plus souvent (toutes les ~3 min) : direction, où est le prix, « branche-toi au marché »
      if (Date.now() - derniereTend > 55000) {   // v7.6 : spectacle +10 %
        const c10 = B.slice(-10).map(x => x[4]), pente = (c10[9] - c10[0]) / moyR, larg = (Math.max(...B.slice(-10).map(x => x[2])) - Math.min(...B.slice(-10).map(x => x[3]))) / moyR;
        const pos = (cur[4] - ll) / Math.max(hh - ll, 1e-9), tour = tendN % 4;   // v8.0 : 4e tour = on fait commenter
        // marché très calme (bougies récentes bien plus petites que d'habitude) → message « va te faire un café » selon l'heure
        const r10 = B.slice(-10).reduce((a, x) => a + (x[2] - x[3]), 0) / 10, r40 = B.reduce((a, x) => a + (x[2] - x[3]), 0) / B.length;
        const h = new Date().getHours(), calme = r10 < 0.6 * r40 && tour !== 2;
        const CAL = h < 6 || h >= 23 ? PHRASES.calme_nuit : h < 11 ? PHRASES.calme_matin : h < 14 ? PHRASES.calme_midi : h < 19 ? PHRASES.calme_aprem : PHRASES.calme_soir;
        // v8.6 (demande d'Adel) : marché calme → un VRAI trader anime le live : questions, pression gentille, « tapote », « commente »
    const narration = commentaireMarcheEnDirect(B, moyR, moyV, m);
        const L = (tendN % 4 !== 3 && narration) ? [narration] : calme ? (pos < 0.25 ? COACH.rebond : pos > 0.75 ? COACH.cassure : [COACH.anim, COACH.anim, PHRASES.ennui, CAL][tendN % 4]) : tour === 3 ? PHRASES.commente : tour === 2 ? PHRASES.branche
          : tour === 1 ? (pos < 0.2 ? PHRASES.bas_zone : pos > 0.8 ? PHRASES.haut_zone : PHRASES.milieu)
          : larg < 3.2 ? PHRASES.range : pente > 1.2 ? PHRASES.hausse : pente < -1.2 ? PHRASES.baisse : PHRASES.range;
        const parleNarration = L.length === 1 && L[0] === narration;   // v12.2.9 : la narration de marché est lue à voix haute
        if (bandeShow(L[Math.floor(tendN / 3) % L.length].replace('{m}', m), parleNarration ? 'marche' : undefined)) {
          if (L === PHRASES.ennui) teteEnnui();
          if (L === PHRASES.bas_zone || L === PHRASES.haut_zone) versBot('zone', L === PHRASES.bas_zone ? -1 : 1);   // la vraie réponse part dans la chaîne du marché
          derniereTend = Date.now(); tendN++;
          coeurs(8, L === PHRASES.commente ? ['💬'] : L === PHRASES.branche ? ['📲', '📡', '⚡', '🧠'] : L === PHRASES.baisse ? ['🔴', '📉', '🌊'] : L === PHRASES.hausse ? ['🟢', '📈', '🚀'] : ['👀', '❤️', '🔥']);
        }
      }
    } catch (e) {}
  }
  setTimeout(() => { barres(40).slice(-1).forEach(b => { const k = nomMarche() + b[0]; ['acc', 'cb', 'ch', 'vol'].forEach(p => deja[p + k] = 1); }); }, 1500);  // rien au démarrage
  const regardT = setInterval(regarder, 5000);

  // compte à rebours de la clôture 15 min : les 45 dernières secondes, gros chrono + « ça va se décider »
  const chronoT = setInterval(() => { try {
    const s = Math.floor(Date.now() / 1000), reste = 900 - (s % 900), r = zoneGraphique();
    const enAttente = !!arme && arme.quart === Math.floor(s / 900) && botAConfirme();   // v12.2.8 : chrono « distribution / accumulation » seulement si le bot confirme
    // v5.8 (demande d'Adel) : le chrono n'est pas là tout le temps : il surgit dans la DERNIÈRE MINUTE puis disparaît à la clôture
    // v8.5 : le bot annonce qu'une position arrive → chrono « attends le feu vert » jusqu'au verdict
    const pa = window.__ALIGN_POS__ && window.__ALIGN_POS__.fin > Date.now() ? window.__ALIGN_POS__ : null;
    if (((reste <= 45 || (enAttente && reste <= 60)) || pa) && !retour) {
      chrono.style.display = 'flex'; chrono.classList.toggle('urgent', reste <= (enAttente ? 30 : 10));
      // v6.6 : le texte clignote jusqu'à l'explosion et alterne français / anglais toutes les 3 s
      const fr = Math.floor(reste / 3) % 2 === 0;
      const lbl = enAttente
        ? (arme.d === -1 ? (fr ? '🔴 GROSSE DISTRIBUTION<br>' : '🔴 BIG SELL-OFF<br>') : (fr ? '🟢 GROSSE ACCUMULATION<br>' : '🟢 BIG ACCUMULATION<br>'))
          + (reste <= 20 ? (fr ? 'CLÔTURE EN COURS' : 'CANDLE CLOSING') : (fr ? 'attends la confirmation • lien en bio' : 'wait for confirmation • link in bio'))
        : (fr ? '⏱ CLÔTURE 15 MIN<br>ça va se décider 👀' : '⏱ 15 MIN CLOSE<br>it\'s about to decide 👀');
      const rr = pa ? Math.max(0, Math.ceil((pa.fin - Date.now()) / 1000)) : reste;
      const lbl2 = pa ? plateforme(fr ? '⚡ UNE POSITION ARRIVE<br>attends le feu vert 👉 lien en bio' : '⚡ A SETUP MAY BE COMING<br>wait for confirmation 👉 link in bio') : lbl;
      chrono.innerHTML = Math.floor(rr / 60) + ':' + String(rr % 60).padStart(2, '0') + '<small>' + lbl2 + '</small>';
      // v5.7 (demande d'Adel) : en bas à droite, côté prix, juste au-dessus du tableau de bord (TikTok coupe le haut gauche)
      // v8.3 (demande d'Adel) : le chrono se met en bas à GAUCHE du tableau, à côté de l'unité 1 min (plus jamais sur un message)
      const mq = masque.style.display === 'flex' ? masque.getBoundingClientRect() : null;
      if (!mq) { chrono.style.width = ''; chrono.style.left = (r.left + r.width - 70 - chrono.offsetWidth - 14) + 'px'; }
      // v5.7 : marché qui baisse → en haut à droite juste sous la bande (les bougies descendent, on ne les cache pas) ;
      //        marché qui monte → en bas à droite, un peu au-dessus du tableau de bord (sans le mordre)
      if (!mq) chrono.style.top = (enAttente && arme.d === -1 ? r.top + 82 : r.top + (r.height || 700) - 205 - chrono.offsetHeight) + 'px';
      // v8.5 (règle d'Adel) : chrono AU-DESSUS des colonnes 1 min / 3 min / 5 min du tableau (3 colonnes sur 11)
      else { const col3 = mq.width * 3 / 11; chrono.style.boxSizing = 'border-box'; chrono.style.width = col3 + 'px'; chrono.style.left = mq.left + 'px'; chrono.style.top = Math.max(r.top + 90, mq.top - mq.height * HAUT_TABLEAU - chrono.offsetHeight - 8) + 'px'; }
      if (reste === 45 && uneFois('cl' + s)) bandeShow('⏱ Clôture 15 min dans 45 s sur ' + nomMarche() + ' • c\'est elle qui décide 👀 • la suite en temps réel : lien en bio 🎁');
    } else if (chrono.style.display !== 'none') {
      chrono.style.display = 'none';
      const b = barres(2)[0];                              // la bougie qui vient de clôturer
      if (b && reste > 880 && arme && arme.quart === Math.floor((s - 60) / 900)) {
        // v6.0 : « ANNONCÉ » seulement si le prix a VRAIMENT bougé dans le sens annoncé depuis l'annonce (au moins ½ bougie moyenne) ;
        // sinon pas de honte : on rassure (« le marché respire, il est comme vous ») et on n'en reparle plus
        const a = arme; arme = null; const pNow = (barres(1)[0] || b)[4]; const mv = (pNow - a.p) * a.d;
        if (mv < 0.5 * (a.r || 1)) {
          versBot('respire', a.d);                 // Telegram : le verdict honnête, pour que personne ne panique
          montrer('😮‍💨 ' + a.m + ' : pas de panique • le marché respire, il est comme vous 😅 • patience, la suite en temps réel : lien en bio 🎁', true, 1, 'proche');
          return;
        }
        { feuArtifice(a.d === -1 ? '📉 ANNONCÉ !' : '📈 ANNONCÉ !'); coeurs(14);
          versBot('annonce', a.d);
      // v8.7 (demande d'Adel) : après le chrono, ça part dans le sens annoncé → « je t'avais prévenu »
      setTimeout(() => montrer('😏 JE T\'AVAIS PRÉVENU ! ' + a.m + (a.d === -1 ? ' 📉' : ' 📈') + PREVENU, false, 1, a.d === -1 ? 'bas' : 'haut', true), 9000);
      pop('✅', 'ANNONCÉ ! ' + a.m + (a.d === -1 ? ' a coulé 📉' : ' a décollé 📈'), a.d, 'la team ALIGN l\'a vu venir • abonne-toi, partage • lien en bio 🎁'); return; }
      }
      if (b && reste > 880) {
        const LG = lignesAlign(), rg = Math.max(b[2] - b[3], 1e-9);
        for (const n of ['TP2', 'TP1', 'SL', 'ENTRÉE']) {
          const l = LG[n]; if (!l || !(b[3] <= l.y && l.y <= b[2]) || Math.abs(b[4] - l.y) < 0.25 * rg) continue;
          const dr = b[4] > l.y ? 1 : -1;            // touchée puis clôture loin de la ligne = rebond / rejet
          pop('↩️', 'REBOND sur une ligne clé ' + nomMarche(), dr, 'le marché prépare quelque chose 👀 pas de panique • pourquoi ? 📲 lien en bio 🎁');
          versBot('rebond', dr, '', n); coeurs(8, ['👀', '↩️', '⚡']);
          return;
        }
      }
      if (b && reste > 880) { const v = b[4] >= b[1] ? 1 : -1; if (!occupe && !file.length) pop(v === 1 ? '🟢' : '🔴', 'BOUGIE 15 MIN CLÔTURÉE ' + (v === 1 ? '⬆️' : '⬇️') + ' ' + nomMarche(), v, 'la suite en temps réel : lien en bio 🎁'); }
    }
  } catch (e) {} }, 1000);
  // de temps en temps des cœurs qui montent : « tapote l'écran »
  const coeurT = setInterval(() => { if (!retour) coeurs(10); }, 80000);   // v7.7 : +12 %

  // v7.4 (demande d'Adel) : position en cours dans le bon sens → petits mots qui font sourire, toutes les 4 min (sans prix)
  let posK = null, posN = 0;
  // v8.9 (demande d'Adel) : pub légère pendant qu'on attend le TP, jamais de prix
  const POS_TXT = ['🔥 LA TEAM, Y\'A DU MONDE DANS LE TRAIN ? 🚂 si t\'es dedans tapote l\'écran et écris OUI 👇 • partage le live pour qu\'il reste tout en haut 🙏',
    '🚀 TU VEUX FAIRE PARTIE DE L\'AVENTURE ? viens tester GRATUITEMENT en compte démo, zéro risque 😉 • tout est dans le lien en bio 👉',
    '😎 ALIGN SUIT SON PLAN… on ne court jamais après un mouvement déjà parti 🚄 • si tu veux suivre la prochaine configuration, consulte le lien en bio',
    '😏 JE SUIS DEDANS AVEC VOUS LA TEAM ! qui est rentré avec moi ? tapote l\'écran 👆 • qui pensait que le marché allait me contredire ? 😝',
    '🍿 ALIGN EST EN POSITION, LE MARCHÉ FAIT LE SPECTACLE… vous, vous tapotez et vous partagez le live 😎 • ceux qui doutaient, on se reparle au TP 😜',
    '😇 TOUT VA BIEN, JE GÈRE… ceux qui sont rentrés sans feu vert, respirez 😂 • tapote si t\'es dans le train avec moi 🚂'];
  EN.push(['😏 JE SUIS DEDANS AVEC VOUS LA TEAM ! qui est rentré avec moi ? tapote l\'écran 👆 • qui pensait que le marché allait me contredire ? 😝', '😏 I\'M IN WITH YOU TEAM! who got in with me? tap the screen 👆 • who thought the market would prove me wrong? 😝'], ['🍿 ALIGN EST EN POSITION, LE MARCHÉ FAIT LE SPECTACLE… vous, vous tapotez et vous partagez le live 😎 • ceux qui doutaient, on se reparle au TP 😜', '🍿 ALIGN IS IN, THE MARKET PUTS ON THE SHOW… you tap and share the live 😎 • doubters, see you at the TP 😜'], ['😇 TOUT VA BIEN, JE GÈRE… ceux qui sont rentrés sans feu vert, respirez 😂 • tapote si t\'es dans le train avec moi 🚂', '😇 ALL GOOD, I\'VE GOT IT… those who jumped in without the green light, breathe 😂 • tap if you\'re on the train with me 🚂']);   // v10.4
  EN.push([POS_TXT[0], '🔥 TEAM, WHO\'S ON THE TRAIN? 🚂 if you\'re in, tap the screen and write YES 👇 • share the live to keep it on top 🙏'],
    [POS_TXT[1], '🚀 WANT TO BE PART OF THE ADVENTURE? try it FOR FREE on a demo account, zero risk 😉 • everything is in the link in bio 👉'],
    [POS_TXT[2], '😎 ALIGN FOLLOWS ITS PLAN… we never chase a move that has already happened 🚄 • to follow the next setup, see the link in bio'],
  );
  const posT = setInterval(() => { try {
    if (retour) return; const LG = lignesAlign(), E = LG['ENTRÉE'], S = LG.SL; if (!E || !S) return;
    const B = barres(3); if (!B.length) return; const p = B[B.length - 1][4], sens = S.y > E.y ? -1 : 1;
    if (sens * (p - E.y) <= 0 || !botDedans(nomMarche())) return;   // v8.5 : seulement si le bot a vraiment donné la position
    // v8.5 (demande d'Adel) : le marché suit le plan → « vous êtes rentrés ? » puis « ça continue, vous êtes contents ? » (jamais de prix)
    const kPos = Math.round(E.y); posN = posK === kPos ? posN + 1 : 0; posK = kPos;
    if (!occupe && !file.length) {
      if (posN === 0) montrer(POS_TXT[0], false, 1);
      else if (posN % 3 === 0) montrer(POS_TXT[2], false, 1);
      else if (posN % 3 === 2) montrer(POS_TXT[1], false, 1);   // v8.9 : pendant qu'on attend le TP → petite pub (sans prix)
      else montrer(POS_TXT[3 + (Math.floor(posN / 3) % 3)], false, 1);   // v10.4 (demande d'Adel) : le bot taquine, fait tapoter et partager
    }
    coeurs(1, ['😊']); setTimeout(() => coeurs(1, ['😏']), 16600);
  } catch (e) {} }, 190000);   // v7.7 : +12 %
  // v8.2 (demande d'Adel) : en live, la ligne du bas du tableau (▼ SHORT E … TP … SL …) ne montre plus les prix :
  // un cache de la même couleur se pose exactement dessus (repéré dans l'image du graphique), sens gardé, prix → « ? » + lien en bio
  const masque = document.createElement('div'); masque.id = 'align-masque'; document.body.appendChild(masque);
  cssPunch.textContent += `
  #align-masque{position:fixed;z-index:140;pointer-events:none;display:none;align-items:center;justify-content:center;gap:10px;color:#fff;
    font:900 13px/1 system-ui,Segoe UI,Arial,sans-serif;   /* v8.4 (Adel) : on garde la couleur d'origine de la ligne, comme en v8.2 (« c'était nickel »), texte un peu plus gros */white-space:nowrap;overflow:hidden;letter-spacing:.3px}
  #align-masque .cle{display:inline-block;animation:emoDanse .6s ease-in-out infinite alternate}
  /* v9.5 (demande d'Adel) : la couleur de la ligne ne doit plus trahir le sens → elle passe du rouge au vert en boucle, avec un reflet en biais */
  #align-masque.mystere{background:linear-gradient(115deg,#c62828 0%,#c62828 40%,#ffd54f 50%,#2e7d32 60%,#2e7d32 100%)!important;background-size:300% 100%!important;
    animation:mystere 2.4s ease-in-out infinite alternate}
  @keyframes mystere{from{background-position:0% 50%}to{background-position:100% 50%}}
  html.align-cache #align-masque{visibility:hidden!important}`;
  let masqueN = 0;
  function celluleSens() {
    try { const mod = chart()._chartWidget.model().model(); let res = null;
      for (const ds of mod.dataSources()) { if (!/ALIGN/.test(String(ds.title && ds.title()))) continue; const vu = new Set();
        (function walk(o, d, dansData) { if (!o || d > 8 || typeof o !== 'object' || vu.has(o) || res) return; vu.add(o);
          if (o instanceof Map) { o.forEach(v => walk(v, d + 1, dansData)); return; }
          if (dansData && typeof o.t === 'string' && typeof o.bgc === 'number') { if (/\b(SHORT|LONG)\b/.test(o.t) && /\d{3,}/.test(o.t)) res = o; return; }
          for (const k of Object.keys(o)) walk(o[k], d + 1, dansData || k === '_primitivesDataById');
        })(ds.graphics()._primitivesCollection.dwgtablecells, 0, false); }
      return res; } catch (e) { return null; }
  }
  function poserMasque() {
    try {
      // Ne jamais révéler le prix sur un raté ponctuel de lecture du canvas : conserver le dernier masque valide.
      // Au premier chargement, le masque reste naturellement caché jusqu'à la première détection fiable.
      const cel = celluleSens(); if (!cel) return;
      const A0 = ((cel.bgc >>> 24) & 255) / 255; let R0 = cel.bgc & 255, G0 = (cel.bgc >> 8) & 255, B0 = (cel.bgc >> 16) & 255;   // v8.4 : couleur parfois transparente
      const cv = document.querySelector('.chart-markup-table .chart-gui-wrapper canvas'); if (!cv) return;
      const R = cv.getBoundingClientRect(), k = cv.width / R.width, W = cv.width, y0 = Math.floor(cv.height * 0.55);
      { const f = cv.getContext('2d').getImageData(3, cv.height - 3, 1, 1).data; R0 = Math.round(A0 * R0 + (1 - A0) * f[0]); G0 = Math.round(A0 * G0 + (1 - A0) * f[1]); B0 = Math.round(A0 * B0 + (1 - A0) * f[2]); }   // mélangée avec le fond
      const d = cv.getContext('2d').getImageData(0, y0, W, cv.height - y0).data; let top = -1, bas = -1, g = 0, dr = 0;
      for (let y = cv.height - y0 - 1; y >= 0; y--) { let n = 0, mi = 1e9, ma = -1;   // v8.3 : on part du BAS (la ligne SHORT/LONG est la dernière du tableau)
        for (let x = 0; x < W; x += 2) { const j = (y * W + x) * 4; if (Math.abs(d[j] - R0) < 8 && Math.abs(d[j + 1] - G0) < 8 && Math.abs(d[j + 2] - B0) < 8) { n++; if (x < mi) mi = x; if (x > ma) ma = x; } }
        if (ma - mi > W * 0.3 && n * 2 > 0.6 * (ma - mi)) { if (bas < 0) { bas = y; g = mi; dr = ma; } top = y; } else if (bas >= 0 && top - y > 1) break; }   // s'arrête au trait entre deux lignes du tableau   // le texte blanc au milieu ne coupe pas la ligne
      // v8.6 (constat d'Adel) : quand la ligne des % est de la même couleur, le cache montait dessus et cachait les % → hauteur limitée à UNE ligne
    if (bas >= 0 && bas - top + 1 > 27 * k) top = bas - Math.round(22 * k);
    if (bas < 0) return;   // v8.4 : si la ligne n'est pas retrouvée un instant, le cache RESTE en place (jamais de prix qui réapparaît)
      Object.assign(masque.style, { display: 'flex', left: (g / k + R.left) + 'px', top: ((top + y0) / k + R.top) + 'px', width: ((dr - g + 2) / k) + 'px',
        height: ((bas - top + 1) / k) + 'px', fontSize: Math.max(13, Math.round((bas - top + 1) / k * 0.8)) + 'px' });   // v9.7 (Adel) : même taille que les % du tableau
      // v9.6 (demande d'Adel) : la ligne CLIGNOTE vert « ▲ LONG ? » / rouge « ▼ SHORT ? » (plus vite quand une entrée approche) → impossible de deviner le sens
      // Correctif : le sens affiché suit le VRAI plan (ligne SHORT/LONG du tableau) ; l'alternance horaire ne sert qu'en secours.
      const vertClignote = Math.floor(Date.now() / (arme ? 600 : 1200)) % 2 === 0;
      const sensReel = ((cel.t || '').match(/\b(SHORT|LONG)\b/) || [])[1];
      const vert = sensReel ? sensReel === 'LONG' : vertClignote;
      masque.classList.remove('mystere'); masque.style.background = !sensReel ? '#4a4a4a' : (vert ? '#1b9e4b' : '#d32f2f');   // sens inconnu : gris neutre, jamais de faux LONG / SHORT
      const en = langueBande() === 'en', sens = (cel.t.match(/[▼▲]?\s*(SHORT|LONG)[^E\d]*/) || [''])[0].trim();
      masque.innerHTML = (masqueN++ % 12 < 8)
        ? (sensReel
          ? '<span class="cle">' + (vert ? '▲' : '▼') + '</span> ' + (vert ? 'LONG ?' : 'SHORT ?') + ' • ' + (en ? 'ENTRY' : 'ENTRÉE') + ' <span class="cle">❓</span> • TP <span class="cle">❓</span> • SL <span class="cle">❓</span>'
          : (en ? 'ENTRY' : 'ENTRÉE') + ' <span class="cle">❓</span> • TP <span class="cle">❓</span> • SL <span class="cle">❓</span>')   // sens inconnu : pas de direction affichée
        : (arme ? '<span class="cle">⏳</span> ' + (en ? 'WAIT FOR CONFIRMATION • VIEW THE PLAN IN BIO' : 'ATTENDS LA CONFIRMATION • VOIR LE PLAN EN BIO')
          : '<span class="cle">🤔</span> ' + (en ? 'WANT TO KNOW IF YOU CAN GET IN? 👍 LINK IN BIO' : 'TU VEUX SAVOIR SI TU PEUX RENTRER ? 👍 LIEN EN BIO'));   // v8.3 : « vite » seulement quand le spectacle a vraiment annoncé un mouvement (pas de fake)
    } catch (e) {}
  }
  // v8.3 (demande d'Adel) : les GROSSES étiquettes ENTRÉE / SL / TP1 / TP2 (à gauche, avec les prix) sont recouvertes
  // et remplacées par des étiquettes courtes « ❓ », toutes de la même taille, alignées sur la colonne du TP2, juste sous leur ligne
  const etiqBox = document.createElement('div'); etiqBox.id = 'align-etiq'; document.body.appendChild(etiqBox);
  cssPunch.textContent += `
  #align-etiq .cache{position:fixed;z-index:139;pointer-events:none;background:rgb(15,15,15);display:flex;align-items:center;justify-content:center;overflow:hidden;
    white-space:nowrap;border-radius:6px;font:900 13px/1 system-ui,Segoe UI,Arial,sans-serif}
  #align-etiq .etq span{display:inline-block;animation:emoDanse .9s ease-in-out infinite alternate}
  #align-etiq .etq.chaud{animation:chaud .6s ease-in-out infinite alternate}
  @keyframes chaud{from{filter:brightness(1)}to{filter:brightness(1.7) saturate(1.4)}}
  #align-etiq .etq{position:fixed;z-index:139;pointer-events:none;box-sizing:border-box;display:flex;align-items:center;justify-content:center;gap:6px;white-space:nowrap;overflow:hidden;padding:0 8px;border-radius:6px;
    font:900 14px/1.15 system-ui,Segoe UI,Arial,sans-serif;box-shadow:0 2px 6px rgba(0,0,0,.45)}
  #align-etiq .etq b{display:inline-block;animation:emoDanse .7s ease-in-out infinite alternate}
  html.align-cache #align-etiq{visibility:hidden!important}`;
  function grossesEtiquettes() {
    const res = [];
    try { const mod = chart()._chartWidget.model().model();
      for (const ds of mod.dataSources()) { if (!/ALIGN/.test(String(ds.title && ds.title()))) continue; const vu = new Set();
        (function walk(o, d, dansData) { if (!o || d > 8 || typeof o !== 'object' || vu.has(o)) return; vu.add(o);
          if (o instanceof Map) { o.forEach(v => walk(v, d + 1, dansData)); return; }
          if (dansData && typeof o.t === 'string' && typeof o.y === 'number') { const n = (o.t.match(/^\s*(ENTRÉE|SL|TP1|TP2)\b/) || [])[1]; if (n && o.st === 'lrg') res.push({ n, o }); return; }
          for (const k of Object.keys(o)) walk(o[k], d + 1, dansData || k === '_primitivesDataById');
        })(ds.graphics()._primitivesCollection.dwglabels, 0, false); } } catch (e) {}
    return res;
  }
  let etiqN = 0;
  const ETIQ_ACTIVES = false;   // v8.3 (décision d'Adel) : PAS d'étiquette posée par-dessus celles du graphique → les étiquettes ENTRÉE/SL/TP se changent dans le script Pine
  function poserEtiquettes() {
    if (!ETIQ_ACTIVES) { etiqBox.innerHTML = ''; return; }
    try {
      const E = grossesEtiquettes(); if (!E.length) { etiqBox.innerHTML = ''; return; }
      const cv = document.querySelector('.chart-markup-table .chart-gui-wrapper canvas'); if (!cv) return;
      const R = cv.getBoundingClientRect(), k = cv.width / R.width, ctx = cv.getContext('2d');
      const ser = chart()._chartWidget.model().mainSeries(), ps = ser.priceScale(), fv = ser.firstValue();
      const boites = [];
      for (const { n, o } of E) {
        const y = ps.priceToCoordinate(o.y, fv); if (!isFinite(y)) continue;
        const fond = ctx.getImageData(Math.round(3 * k), Math.round(y * k), 1, 1).data;   // v8.3 : la vraie couleur de fond de l'écran (plus de tache noire)
        const a = ((o.ci >>> 24) & 255) / 255, col = [o.ci & 255, (o.ci >> 8) & 255, (o.ci >> 16) & 255].map((v, i) => Math.round(a * v + (1 - a) * fond[i]));
        const y0 = Math.max(0, Math.round((y - 18) * k)), hh = Math.round(36 * k), W = Math.round(cv.width * 0.75), d = ctx.getImageData(0, y0, W, hh).data;
        // v8.3 : on mesure le CORPS de l'étiquette (colonnes colorées sur au moins 9 px de haut) : la ligne fine de même couleur ne compte pas
        const ok = j => Math.abs(d[j] - col[0]) < 14 && Math.abs(d[j + 1] - col[1]) < 14 && Math.abs(d[j + 2] - col[2]) < 14;
        const cnt = new Uint16Array(W); for (let yy = 0; yy < hh; yy++) for (let x = 0; x < W; x++) if (ok((yy * W + x) * 4)) cnt[x]++;
        const minH = Math.round(9 * k); let mi = -1, ma = -1;
        for (let x = 0; x < W; x++) { if (cnt[x] >= minH) { if (mi < 0) mi = x; ma = x; } else if (mi >= 0 && x - ma > Math.round(8 * k)) break; }
        let yt = 1e9, yb = -1;
        if (mi >= 0) for (let yy = 0; yy < hh; yy++) { let n = 0; for (let x = mi; x <= ma; x++) if (ok((yy * W + x) * 4)) n++; if (n > (ma - mi + 1) * 0.5) { if (yy < yt) yt = yy; if (yy > yb) yb = yy; } }
        if (mi < 0 || yb < 0) { mi = 1e9; ma = -1; }
        boites.push({ n, o, y, fond: 'rgb(' + fond[0] + ',' + fond[1] + ',' + fond[2] + ')', col: 'rgb(' + col.join(',') + ')', tc: (o.tci & 255) > 128 ? '#fff' : '#111', box: ma > mi + 20 ? { l: mi / k + R.left, t: (y0 + yt) / k + R.top, r: (ma + 1) / k + R.left, b: (y0 + yb + 1) / k + R.top } : null });
      }
      // v8.3 (demande d'Adel : « j'ai l'impression que tu en as mis deux » + « petites bandes noires ») : UNE seule étiquette par ligne,
      // posée exactement sur l'étiquette d'origine (plus de doublon, plus de cache noir), toutes alignées et de la même largeur,
      // le prix remplacé par « ❓ » + un petit défi qui change, qui clignote quand le prix s'approche
      const vis = boites.filter(x => x.box); if (!vis.length) { etiqBox.innerHTML = ''; return; }
      const xCol = Math.min(...vis.map(x => x.box.l)), larg = Math.max(...vis.map(x => x.box.r)) - xCol, en = langueBande() === 'en';
      const pNow = ((barres(1)[0]) || [])[4] || 0; etiqN++;
      const proche = x => pNow && Math.abs(pNow - x.o.y) / pNow < 0.002;
      const defi = x => { const L = proche(x) ? (en ? ['⚡ KEY ZONE APPROACHING', '👉 VIEW THE PLAN'] : ['⚡ ZONE CLÉ EN APPROCHE', '👉 VOIR LE PLAN'])
        : (en ? ['👀 LINK IN BIO', '🤔 WANNA KNOW?', '😏 DARE YOU?'] : ['👀 LIEN EN BIO', '🤔 T\'AS ENVIE DE SAVOIR ?', '😏 CAP OU PAS CAP ?']); return L[Math.floor(etiqN / 12) % L.length]; };
      etiqBox.innerHTML = vis.map(x => '<div class="etq' + (proche(x) ? ' chaud' : '') + '" style="left:' + (xCol - 2) + 'px;top:' + (x.box.t - 2) + 'px;width:' + (larg + 4) + 'px;height:' + (x.box.b - x.box.t + 4) + 'px;background:' + x.col + ';color:' + x.tc + '">'
        + (x.n === 'ENTRÉE' && en ? 'ENTRY' : x.n) + ' <b>❓</b> <span>' + defi(x) + '</span></div>').join('');
    } catch (e) {}
  }
  const etiqT = setInterval(poserEtiquettes, 300);
  // v8.3 (demande d'Adel) : quand tu bouges / zoomes le graphique, les étiquettes et le cache suivent tout de suite
  let suitT = 0; ['wheel', 'pointermove'].forEach(ev => document.addEventListener(ev, e => { if (!vivant || (ev === 'pointermove' && !e.buttons) || suitT) return;
    suitT = requestAnimationFrame(() => { suitT = 0; poserEtiquettes(); poserMasque(); }); }, { passive: true, capture: true }));   // v8.3 : suit le graphique quand tu bouges la souris poserEtiquettes();
  const masqueT = setInterval(poserMasque, 300); poserMasque();
  window.__ALIGN_BANDE__ = {
    version: VERSION, recu, punch: c => coeurs(1, [c]), plateforme: v => choisirPlateforme(v),
    stop() { vivant = false; clearTimeout(survolT); cancelAnimationFrame(raf); clearInterval(suivi); clearInterval(coachT); clearInterval(iaT); clearInterval(astuceT); clearInterval(regardT); clearInterval(chronoT); clearInterval(coeurT); clearInterval(posT); clearInterval(botEtatSyncT); clearInterval(heartbeatT); clearInterval(masqueT); try { window.speechSynthesis && window.speechSynthesis.cancel(); window.speechSynthesis && window.speechSynthesis.removeEventListener('voiceschanged', voixSurVoixChangees); voixEnAttente = null; } catch (e) {} try { controlsDock.remove(); } catch (e) {} try { voixBtn.remove(); } catch (e) {} try { voixLangueBtn.remove(); } catch (e) {} try { animationsBtn.remove(); cssAnimationsToggle.remove(); document.documentElement.classList.remove('align-animations-off'); } catch (e) {} masque.remove(); try { cssPunch.remove(); } catch (e) {}   /* v8.4 : plus de vieux styles qui restent après une réinjection */ clearInterval(etiqT); etiqBox.remove(); try { cssEnnui.remove(); document.getElementById('align-ennui')?.remove(); } catch (e) {}
      [cadre, chrono, cssShow].forEach(x => { try { x.remove(); } catch (e) {} }); document.querySelectorAll('.align-coeur,.align-billet,.align-argent,.align-punch,.align-ping').forEach(x => x.remove()); try { cssBillet.remove(); } catch (e) {} obs.disconnect(); try { es.close(); } catch (e) {} bande.remove(); css.remove(); }
  };
})();
