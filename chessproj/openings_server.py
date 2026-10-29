#!/usr/bin/env python3
"""
Opening explorer: a web page of opening and famous-game buttons that plays the
chosen line on the Sense HAT 8x8 LED matrix, with a description and move notes.

    python3 openings_server.py
    then open  http://ryanpi.local:8000  on a phone or laptop on the same Wi-Fi

Needs: sense_hat and python-chess   (pip install chess --break-system-packages)
Colours and LED setup come from panel.py, so they match colorchess/followchess;
a white flash marks the square a piece just moved to. Joystick up/down = brightness.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import chess

from panel import DARK_SQUARE, FLASH_TO, LIGHT_SQUARE, PIECE_COLOURS, scaled, sense

# ---------------------------------------------------------------- settings

PORT = 8000
FLASH_SECONDS = 0.35
DEFAULT_DELAY = 1.2       # seconds between moves (the page slider overrides this)
FLASH_FROM = (70, 70, 60)

# ---------------------------------------------------------------- openings
#
# To add one, copy a block and change it:
#   moves  normal chess notation, pasted from Lichess / Wikipedia is fine
#   about  a short description shown under the board
#   notes  optional comments on single moves: "3.Bc4" is White's 3rd move,
#          "3...Bc5" is Black's 3rd move
# A typo stops the server at startup and tells you exactly what's wrong.

OPENING_LINES = [
    {
        "id": "italian", "name": "Italian Game", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O Re1 a6 Bb3 Ba7 h3 h6 Nbd2 Re8",
        "about": "One of the oldest openings. White develops quickly and points the bishop at f7, "
                 "the weakest square near Black's king. This slow version with c3 and d3 "
                 "(the 'Giuoco Pianissimo') is a favourite of top players: both sides castle "
                 "and manoeuvre before committing to a plan.",
        "notes": {
            "2.Nf3": "Attacks the e5 pawn while developing.",
            "2...Nc6": "Defends e5 and develops.",
            "3.Bc4": "The Italian bishop, aimed straight at f7.",
            "3...Bc5": "Black mirrors White and aims at f2.",
            "4.c3": "Prepares d4 to grab the centre later.",
            "5.d3": "The quiet approach: a solid centre and no early fight.",
            "7...a6": "Makes room for the bishop to drop back to a7 without being traded.",
            "9.h3": "Stops ...Bg4, which would pin the knight.",
            "10.Nbd2": "The knight is heading for f1 and g3, a typical Italian route.",
        },
    },
    {
        "id": "ruy", "name": "Ruy Lopez", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7",
        "about": "Named after a 16th-century Spanish priest, the Ruy Lopez is one of the most "
                 "deeply studied openings in chess. White pressures the knight that defends e5 "
                 "and builds slow, lasting pressure. This is the Closed Ruy Lopez, Chigorin Variation.",
        "notes": {
            "3.Bb5": "Attacks the knight that defends e5.",
            "3...a6": "The Morphy Defence: asks the bishop to decide right away.",
            "5.O-O": "White castles. Taking on e4 is possible but leads to the sharp Open Ruy Lopez.",
            "6.Re1": "Now e4 is defended, and White threatens Bxc6 followed by Nxe5.",
            "6...b5": "Kicks the bishop and gains space on the queenside.",
            "8.c3": "Prepares d4 and gives the bishop a retreat square on c2.",
            "9.h3": "Stops ...Bg4, which would pin the knight and weaken d4.",
            "9...Na5": "The Chigorin plan: chase the strong bishop, then play ...c5.",
            "11.d4": "White finally claims the centre with pawns.",
        },
    },
    {
        "id": "kingsgambit", "name": "King's Gambit", "group": "1.e4",
        "moves": "e4 e5 f4 exf4 Nf3 g5 h4 g4 Ne5 Nf6 d4 d6 Nd3 Nxe4 Bxf4 Bg7 c3 Qe7 Qe2 Bf5",
        "about": "A romantic 19th-century favourite. White gives up a pawn to rip open the f-file "
                 "and build a big centre, hoping for a fast attack. Black can grab material but "
                 "has to survive the storm. This line is the Kieseritzky Gambit.",
        "notes": {
            "2.f4": "The gambit: offers a pawn to pull Black's e-pawn away from the centre.",
            "2...exf4": "Black accepts the pawn.",
            "3...g5": "Holds on to the extra pawn on f4.",
            "4.h4": "Undermines the g5 pawn that protects f4.",
            "5.Ne5": "The Kieseritzky: the knight jumps to a strong central square.",
            "7...Nxe4": "Black grabs a second pawn.",
            "8.Bxf4": "White wins a pawn back and gets the bishop into the game.",
        },
    },
    {
        "id": "friedliver", "name": "Fried Liver Attack", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7 Qf3+ Ke6 Nc3 Ncb4 a3 Nxc2+ Kd1 Nxa1 Nxd5 Qh4",
        "about": "A wild attacking line from the Two Knights Defence. White sacrifices a knight on "
                 "f7 to drag Black's king into the middle of the board. It's dangerous and fun, "
                 "but Black can sidestep it completely with 5...Na5 instead of 5...Nxd5.",
        "notes": {
            "3...Nf6": "The Two Knights Defence: counterattacks e4.",
            "4.Ng5": "Teams up with the bishop against f7.",
            "4...d5": "Blocks the bishop's diagonal.",
            "5...Nxd5": "The natural recapture, but it walks into the Fried Liver.",
            "6.Nxf7": "The sacrifice! The knight forks queen and rook, so the king has to take.",
            "7.Qf3+": "Checks the king and attacks the knight on d5.",
            "7...Ke6": "The king steps forward to defend d5. It's now in the centre of the board.",
            "8...Ncb4": "Defends d5 again and eyes c2.",
            "9...Nxc2+": "Black counterattacks, forking king and rook.",
            "11.Nxd5": "White gives up the rook and piles onto d5 while Black's king is still exposed.",
        },
    },
    {
        "id": "scholars", "name": "Scholar's Mate", "group": "1.e4",
        "moves": "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#",
        "about": "Not a real opening but the most famous beginner trap. The queen and bishop both "
                 "aim at f7, which only Black's king defends. Easy to stop with ...g6 or ...Qe7 "
                 "once you know it.",
        "notes": {
            "3.Qh5": "Threatens Qxf7 checkmate, and also attacks e5.",
            "3...Nf6": "A natural-looking blunder: it attacks the queen but ignores f7.",
            "4.Qxf7#": "Checkmate. The bishop on c4 protects the queen, so the king can't take it.",
        },
    },
    {
        "id": "najdorf", "name": "Sicilian Najdorf", "group": "1.e4",
        "moves": "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be3 e5 Nb3 Be6 f3 Be7 Qd2 O-O O-O-O Nbd7 g4 b5",
        "about": "The Sicilian is Black's sharpest reply to 1.e4, and the Najdorf is its most famous "
                 "form, played by Fischer and Kasparov. Black trades a side pawn for a centre pawn "
                 "and plays for the win. In this English Attack, the players castle on opposite "
                 "sides and race to attack each other's kings.",
        "notes": {
            "1...c5": "The Sicilian: fights for d4 without mirroring White.",
            "3...cxd4": "Black trades a side pawn for a centre pawn.",
            "5...a6": "The Najdorf move: keeps White's pieces off b5 and prepares ...b5.",
            "6.Be3": "The English Attack begins: Be3, f3, Qd2, castle queenside, then g4.",
            "6...e5": "Kicks the knight and grabs space in the centre.",
            "10.O-O-O": "Opposite-side castling: now it's a race.",
            "11.g4": "White's pawns storm toward Black's king.",
            "11...b5": "Black's pawn storm on the other wing.",
        },
    },
    {
        "id": "french", "name": "French Defense", "group": "1.e4",
        "moves": "e4 e6 d4 d5 Nc3 Nf6 Bg5 Be7 e5 Nfd7 Bxe7 Qxe7 f4 O-O Nf3 c5 Qd2 Nc6 O-O-O c4",
        "about": "A solid counterpunching defence. Black lets White build a big pawn centre, then "
                 "attacks its base with ...c5 and ...f6. The downside is Black's light-squared "
                 "bishop, which gets stuck behind the e6 pawn.",
        "notes": {
            "1...e6": "Prepares ...d5 to challenge e4.",
            "2...d5": "Hits the e4 pawn straight away.",
            "4.Bg5": "Pins the knight that attacks e4.",
            "5.e5": "Gains space and kicks the knight.",
            "7.f4": "Supports e5, the spearhead of White's centre.",
            "8...c5": "The typical French strike at White's pawn chain.",
            "10.O-O-O": "Opposite-side castling: both sides will attack.",
            "10...c4": "Black gains space and gets ready to storm the queenside.",
        },
    },
    {
        "id": "caro", "name": "Caro-Kann", "group": "1.e4",
        "moves": "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 Qxd3 e6 Bd2 Ngf6 O-O-O Be7",
        "about": "A rock-solid defence. Like the French, Black challenges e4 with ...d5, but plays "
                 "...c6 first so the light-squared bishop can get out before ...e6. Black aims for "
                 "a sound position with no weaknesses.",
        "notes": {
            "1...c6": "Prepares ...d5 while keeping the bishop's diagonal open.",
            "3...dxe4": "Black gives up the centre in exchange for easy development.",
            "4...Bf5": "The Classical: the bishop gets out before ...e6 shuts it in.",
            "5.Ng3": "Kicks the bishop with tempo.",
            "6.h4": "Threatens h5, which would trap the bishop.",
            "8.h5": "Grabs space and makes Black's kingside harder to use.",
            "9.Bd3": "Offers a trade of light-squared bishops.",
        },
    },
    {
        "id": "scandi", "name": "Scandinavian", "group": "1.e4",
        "moves": "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 c6 Bc4 Bf5 Bd2 e6 Nd5 Qd8 Nxf6+ Qxf6 Qe2 Nd7",
        "about": "Black hits e4 on move one and recaptures with the queen. The queen gets chased "
                 "around a little, but Black ends up with a simple, solid position and easy "
                 "development, much like a Caro-Kann.",
        "notes": {
            "1...d5": "Attacks e4 immediately.",
            "2...Qxd5": "The queen recaptures early, accepting that it'll be chased.",
            "3.Nc3": "Develops while attacking the queen.",
            "3...Qa5": "The queen steps aside and will pin the c3 knight against the king.",
            "5...c6": "Gives the queen a retreat on c7 and controls d5.",
            "6...Bf5": "The light-squared bishop gets out before ...e6.",
            "7.Bd2": "Breaks the pin, so the c3 knight is free to move.",
            "8.Nd5": "Discovered attack: the knight jumps away and the d2 bishop now hits the queen.",
        },
    },
    {
        "id": "qgd", "name": "Queen's Gambit Declined", "group": "1.d4",
        "moves": "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7 Rc1 c6 Bd3 dxc4 Bxc4 Nd5 Bxe7 Qxe7 O-O Nxc3 Rxc3 e5",
        "about": "One of the most classical openings. White offers the c-pawn to pull Black's "
                 "d-pawn away from the centre. Black declines with ...e6 and keeps a strong point "
                 "on d5. This is the Orthodox Defence, finished with Capablanca's freeing manoeuvre.",
        "notes": {
            "2.c4": "The gambit: offers a pawn to pull Black's d-pawn away from the centre.",
            "2...e6": "Declines, keeping d5 solidly defended.",
            "4.Bg5": "Pins the knight that guards d5.",
            "7.Rc1": "The rook lines up on the c-file, which will open later.",
            "8...dxc4": "Black finally takes, timed so White's bishop has to move twice.",
            "9...Nd5": "Capablanca's idea: trade pieces to free Black's cramped position.",
            "12...e5": "The freeing pawn break Black was playing for.",
        },
    },
    {
        "id": "qga", "name": "Queen's Gambit Accepted", "group": "1.d4",
        "moves": "d4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5 O-O a6 dxc5 Qxd1 Rxd1 Bxc5 Kf1 b5 Be2 Bb7",
        "about": "White offers the c-pawn and Black takes it. Black isn't trying to keep the pawn: "
                 "the point is to let White take the centre, then hit back with ...c5. White wins "
                 "the pawn back easily and the game turns calm and positional.",
        "notes": {
            "2...dxc4": "Black accepts the pawn, but won't try to keep it.",
            "4.e3": "Opens the bishop's diagonal to win c4 back.",
            "5.Bxc4": "White regains the pawn.",
            "5...c5": "Black's key strike at the centre.",
            "7.dxc5": "Trading queens leads to a calm, roughly equal endgame.",
            "9.Kf1": "With the queens gone, the king heads for the centre, where it's useful.",
        },
    },
    {
        "id": "kid", "name": "King's Indian", "group": "1.d4",
        "moves": "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7 Ne1 Nd7 Nd3 f5 Bd2 Nf6 f3 f4",
        "about": "A fighting, hypermodern defence and Kasparov's favourite. Black lets White build "
                 "a huge centre, tucks the king behind the bishop on g7, then counterattacks. In "
                 "this Mar del Plata line, White attacks on the queenside while Black throws "
                 "everything at White's king.",
        "notes": {
            "2...g6": "Prepares to put the bishop on g7.",
            "4.e4": "White takes a big pawn centre, and Black lets it happen.",
            "6...e5": "Black finally strikes at the centre.",
            "8.d5": "Locks the centre. Now each side attacks on its own wing.",
            "9.Ne1": "The knight reroutes to d3 to support a queenside attack with c5.",
            "10...f5": "Black's key pawn break toward White's king.",
            "12...f4": "Black gains space and gets ready to push ...g5 and ...g4.",
        },
    },
    {
        "id": "london", "name": "London System", "group": "1.d4",
        "moves": "d4 d5 Bf4 Nf6 e3 e6 Nf3 c5 c3 Nc6 Nbd2 Bd6 Bg3 O-O Bd3 b6 Ne5 Bb7 f4 Ne7",
        "about": "A system rather than a sharp opening: White plays the same set-up against almost "
                 "anything. The bishop goes to f4 before e3 so it isn't locked in, then White "
                 "builds a solid pyramid of pawns. Easy to learn and very popular at club level.",
        "notes": {
            "2.Bf4": "The London bishop, developed before e3 shuts it in.",
            "3.e3": "Starts the solid pawn chain on c3, d4 and e3.",
            "5.c3": "Completes the pawn pyramid supporting d4.",
            "6...Bd6": "Black challenges White's bishop.",
            "7.Bg3": "Keeps the bishop. If Black trades, hxg3 opens the h-file for White's rook.",
            "9.Ne5": "The knight jumps to a strong outpost.",
            "10.f4": "Supports the knight and prepares a kingside attack.",
        },
    },
    {
        "id": "english", "name": "English Opening", "group": "Other",
        "moves": "c4 e5 Nc3 Nf6 Nf3 Nc6 g3 d5 cxd5 Nxd5 Bg2 Nb6 O-O Be7 d3 O-O a3 Be6 b4 f6",
        "about": "White starts on the side with 1.c4, controlling d5 without committing in the "
                 "centre. Against 1...e5 it's a Sicilian with colours reversed, so White has a "
                 "whole extra move. The bishop on g2 rakes the long diagonal.",
        "notes": {
            "1.c4": "Controls d5 from the side.",
            "1...e5": "Black takes the centre: a reversed Sicilian.",
            "4...d5": "Black grabs the centre with pawns.",
            "6.Bg2": "The bishop on g2 pressures the long diagonal toward b7 and c6.",
            "10.b4": "White grabs space on the queenside.",
            "10...f6": "Shores up e5 so the c6 knight is free to move.",
        },
    },

# ------------------------------------------------ more 1.e4 openings
    {
        "id": "scotch", "name": "Scotch Game", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nxc6 bxc6 e5 Qe7 Qe2 Nd5 c4 Ba6 b3 g6 f4 f6",
        "about": "Instead of the slow build-up of the Italian or Ruy Lopez, White opens the centre "
                 "on move three. A favourite of Kasparov. This is the Mieses Variation, where White "
                 "trades knights to damage Black's pawns and then grabs space.",
        "notes": {
            "3.d4": "Opens the centre straight away.",
            "3...exd4": "Black has to take, or the e5 pawn falls.",
            "4...Nf6": "Develops and attacks e4.",
            "5.Nxc6": "The Mieses: trades knights to double Black's pawns.",
            "6.e5": "Kicks the knight off f6.",
            "6...Qe7": "Attacks the e5 pawn, which White has to defend.",
            "8.c4": "Chases the knight away from the centre.",
            "8...Ba6": "Pins the c4 pawn to White's queen.",
            "10...f6": "Black strikes at e5 to open lines.",
        },
    },
    {
        "id": "petrov", "name": "Petrov Defense", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 d4 d5 Bd3 Nc6 O-O Be7 c4 Nb4 Be2 O-O Nc3 Bf5 a3 Nxc3 bxc3 Nc6",
        "about": "Also called the Russian Game. Black ignores the attack on e5 and counterattacks "
                 "e4 instead. It's famous for being very solid and hard to beat, which makes it a "
                 "popular drawing weapon at top level.",
        "notes": {
            "2...Nf6": "Counterattacks e4 instead of defending e5.",
            "3...d6": "Kicks the knight first. Taking on e4 straight away runs into Qe2.",
            "4...Nxe4": "Now Black wins the pawn back.",
            "5.d4": "Takes the centre and prepares Bd3 to challenge the e4 knight.",
            "8.c4": "Undermines d5, which supports Black's knight.",
            "8...Nb4": "Hits the bishop on d3.",
            "11.a3": "Kicks the knight off b4.",
            "12...Nc6": "The knight comes back, and the position is about level.",
        },
    },
    {
        "id": "vienna", "name": "Vienna Gambit", "group": "1.e4",
        "moves": "e4 e5 Nc3 Nf6 f4 d5 fxe5 Nxe4 Nf3 Be7 d4 O-O Bd3 f5 exf6 Bxf6 O-O Nc6",
        "about": "White develops the queen's knight first, keeping the f-pawn free to advance. "
                 "Then f4 turns it into a kind of King's Gambit with an extra piece already out. "
                 "Black's best answer is to strike back in the centre with ...d5.",
        "notes": {
            "2.Nc3": "Develops and guards e4, keeping the f-pawn free.",
            "3.f4": "The gambit: attacks e5 and prepares to open the f-file.",
            "3...d5": "The best reply: Black hits back in the centre.",
            "4...Nxe4": "The knight lands on a strong central square.",
            "7...f5": "Supports the e4 knight.",
            "8.exf6": "En passant! White captures the pawn that just moved past e5.",
        },
    },
    {
        "id": "philidor", "name": "Philidor Defense", "group": "1.e4",
        "moves": "e4 e5 Nf3 d6 d4 Nf6 Nc3 Nbd7 Bc4 Be7 O-O O-O Re1 c6 a4 b6",
        "about": "Named after François-André Philidor, the best player of the 18th century. Black "
                 "defends e5 with a pawn and keeps a solid, compact position. This modern "
                 "Hanham set-up holds e5 with the knight and prepares slow queenside play.",
        "notes": {
            "2...d6": "Defends e5 with a pawn, but blocks the f8 bishop.",
            "4...Nbd7": "The Hanham set-up: Black keeps a firm grip on e5.",
            "7...c6": "Prepares ...b5 and gives the queen a route to c7.",
            "8.a4": "Stops ...b5 and gains space on the queenside.",
        },
    },
    {
        "id": "dragon", "name": "Sicilian Dragon", "group": "1.e4",
        "moves": "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O Qd2 Nc6 Bc4 Bd7 O-O-O Rc8 Bb3 Ne5 h4 h5",
        "about": "Black's pawns on d6, e7, f7, g6 and h7 look like a dragon. The bishop on g7 "
                 "breathes fire down the long diagonal. In this Yugoslav Attack both sides castle "
                 "on opposite wings, and it's a race to checkmate first.",
        "notes": {
            "5...g6": "The Dragon: the bishop goes to g7 to rake the long diagonal.",
            "6.Be3": "The Yugoslav Attack: Be3, f3, Qd2, castle long, then push pawns.",
            "7.f3": "Stops ...Ng4 from chasing the bishop.",
            "10.O-O-O": "Opposite-side castling: now it's a race.",
            "10...Rc8": "The rook takes the open c-file toward White's king.",
            "12.h4": "White plans h5 to open the h-file against Black's king.",
            "12...h5": "Black blocks the h-pawn.",
        },
    },
    {
        "id": "sveshnikov", "name": "Sicilian Sveshnikov", "group": "1.e4",
        "moves": "e4 c5 Nf3 Nc6 d4 cxd4 Nxd4 Nf6 Nc3 e5 Ndb5 d6 Bg5 a6 Na3 b5 Bxf6 gxf6 Nd5 f5",
        "about": "A bold Sicilian where Black plays ...e5, accepting a permanent hole on d5 in "
                 "exchange for active pieces. Black ends up with ugly-looking pawns but the "
                 "bishop pair and lots of activity. Magnus Carlsen has used it in world "
                 "championship matches.",
        "notes": {
            "5...e5": "The Sveshnikov: kicks the knight, at the cost of a hole on d5.",
            "6.Ndb5": "Eyes d6, which ...e5 weakened.",
            "7...a6": "Drives the knight to the edge of the board.",
            "9.Bxf6": "Gives up the bishop to wreck Black's pawns and win control of d5.",
            "10.Nd5": "The knight lands on the square Black left open.",
            "10...f5": "Black uses the pawns to fight for the centre.",
        },
    },
    {
        "id": "alapin", "name": "Sicilian Alapin", "group": "1.e4",
        "moves": "e4 c5 c3 Nf6 e5 Nd5 d4 cxd4 Nf3 Nc6 cxd4 d6 Bc4 Nb6 Bb5 dxe5 Nxe5 Bd7",
        "about": "A practical way to avoid the main-line Sicilian. White plays c3 so that after "
                 "d4 and ...cxd4 a pawn can recapture, giving White the ideal two-pawn centre. "
                 "It's a favourite at club level because it avoids a lot of theory.",
        "notes": {
            "2.c3": "The Alapin: prepares d4 so a pawn can recapture.",
            "2...Nf6": "Hits e4 straight away.",
            "3.e5": "Kicks the knight, like in the Alekhine Defence.",
            "6.cxd4": "White now has two pawns in the centre.",
            "7...Nb6": "Hits the bishop on c4.",
            "8.Bb5": "Pins the c6 knight to Black's king.",
        },
    },
    {
        "id": "pirc", "name": "Pirc Defense", "group": "1.e4",
        "moves": "e4 d6 d4 Nf6 Nc3 g6 f4 Bg7 Nf3 O-O Bd3 Na6 O-O c5 d5 Bg4",
        "about": "A hypermodern defence. Black lets White build a big centre, puts the bishop on "
                 "g7 and waits for the right moment to strike. This is the aggressive Austrian "
                 "Attack, where White grabs as much space as possible.",
        "notes": {
            "1...d6": "The Pirc: Black lets White take the centre and plans to hit it later.",
            "3...g6": "The bishop heads for g7.",
            "4.f4": "The Austrian Attack: White grabs lots of space.",
            "7...c5": "Black strikes at d4.",
            "8.d5": "White gains more space instead of trading.",
            "8...Bg4": "Pins the f3 knight to White's queen.",
        },
    },
    {
        "id": "alekhine", "name": "Alekhine Defense", "group": "1.e4",
        "moves": "e4 Nf6 e5 Nd5 d4 d6 Nf3 Bg4 Be2 e6 O-O Be7 h3 Bh5 c4 Nb6 exd6 cxd6 Nc3 O-O Be3 d5",
        "about": "Named after world champion Alexander Alekhine. Black's knight provokes White's "
                 "pawns forward, hoping they'll become overextended targets. A provocative and "
                 "unusual defence.",
        "notes": {
            "1...Nf6": "The Alekhine: invites White's pawns forward.",
            "2.e5": "Kicks the knight.",
            "3...d6": "Attacks the e5 pawn.",
            "4...Bg4": "Pins the knight that defends e5.",
            "8.c4": "Kicks the knight again.",
            "9.exd6": "White trades on d6 rather than overextend.",
            "11...d5": "Black hits c4 and claims some central space.",
        },
    },
    # ------------------------------------------------ more 1.d4 openings
    {
        "id": "slav", "name": "Slav Defense", "group": "1.d4",
        "moves": "d4 d5 c4 c6 Nf3 Nf6 Nc3 dxc4 a4 Bf5 e3 e6 Bxc4 Bb4 O-O Nbd7 Qe2 Bg6 e4 O-O",
        "about": "Black defends d5 with ...c6 instead of ...e6, so the light-squared bishop can get "
                 "out before the pawn chain closes. One of the most solid answers to the Queen's "
                 "Gambit.",
        "notes": {
            "2...c6": "The Slav: defends d5 and keeps the c8 bishop's diagonal open.",
            "4...dxc4": "Black takes the pawn, hoping to hold it with ...b5.",
            "5.a4": "Stops ...b5, so White will win the pawn back.",
            "5...Bf5": "The bishop gets out before ...e6.",
            "7.Bxc4": "White regains the pawn.",
            "10.e4": "White finally gets the e4 push in.",
        },
    },
    {
        "id": "semislav", "name": "Semi-Slav (Meran)", "group": "1.d4",
        "moves": "d4 d5 c4 c6 Nf3 Nf6 Nc3 e6 e3 Nbd7 Bd3 dxc4 Bxc4 b5 Bd3 Bb7 O-O a6 e4 c5 d5 Qc7",
        "about": "A mix of the Slav and the Queen's Gambit Declined. In the Meran Variation, Black "
                 "takes on c4 and uses the time to expand on the queenside. It leads to sharp, "
                 "complicated positions.",
        "notes": {
            "4...e6": "The Semi-Slav: both ...c6 and ...e6.",
            "6...dxc4": "Black takes once White's bishop has moved, gaining a tempo.",
            "7...b5": "The Meran: kicks the bishop and grabs queenside space.",
            "8...Bb7": "The bishop lines up on the long diagonal.",
            "10.e4": "White claims the centre.",
            "10...c5": "Black hits back at d4.",
            "11.d5": "White pushes past, opening lines while Black's king is uncastled.",
        },
    },
    {
        "id": "nimzo", "name": "Nimzo-Indian", "group": "1.d4",
        "moves": "d4 Nf6 c4 e6 Nc3 Bb4 Qc2 O-O a3 Bxc3+ Qxc3 b6 Bg5 Bb7 f3 h6 Bh4 d5 e3 Nbd7",
        "about": "Named after Aron Nimzowitsch. Black pins the c3 knight so White can't easily play "
                 "e4, and is happy to give up the bishop to damage White's pawns. One of the most "
                 "respected defences to 1.d4.",
        "notes": {
            "3...Bb4": "The Nimzo-Indian: the pin makes e4 hard for White.",
            "4.Qc2": "The Classical: White can recapture on c3 with the queen, keeping the pawns healthy.",
            "5.a3": "Asks the bishop to decide.",
            "5...Bxc3+": "Black gives up the bishop pair.",
            "7...Bb7": "Fights for e4 from a distance.",
            "8.f3": "Prepares e4.",
            "9...d5": "Black grabs the centre before e4 arrives.",
        },
    },
    {
        "id": "qid", "name": "Queen's Indian", "group": "1.d4",
        "moves": "d4 Nf6 c4 e6 Nf3 b6 g3 Ba6 b3 Bb4+ Bd2 Be7 Bg2 c6 Bc3 d5 Ne5 Nfd7 Nxd7 Nxd7 Nd2 O-O O-O",
        "about": "Black fianchettoes the queen's bishop to control the centre from the side, "
                 "especially the e4 square. A calm, solid defence that's hard to crack.",
        "notes": {
            "3...b6": "The Queen's Indian: the bishop will control e4 from the flank.",
            "4...Ba6": "Hits the c4 pawn.",
            "5...Bb4+": "Lures White's bishop to d2, where it's a bit in the way.",
            "8...d5": "Black stakes a claim in the centre.",
            "9.Ne5": "The knight jumps forward, ready to trade.",
        },
    },
    {
        "id": "grunfeld", "name": "Grünfeld Defense", "group": "1.d4",
        "moves": "d4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7 Bc4 c5 Ne2 Nc6 Be3 O-O O-O Bg4 f3 Na5 Bd5 Bd7 Rb1 a6",
        "about": "A dynamic hypermodern defence. Black lets White build a huge pawn centre, then "
                 "attacks it with the g7 bishop, ...c5 and the knights. Kasparov and many other "
                 "world champions have played it.",
        "notes": {
            "3...d5": "The Grünfeld: Black challenges the centre right away.",
            "5.e4": "White builds a big centre and gains time on the knight.",
            "6.bxc3": "White's centre is huge, and Black's whole plan is to attack it.",
            "7...c5": "The first strike at d4.",
            "8.Ne2": "The knight goes to e2 to support d4 without being pinned.",
            "10...Bg4": "Adds pressure on d4 by hitting the e2 knight.",
            "11...Na5": "Black leaves the bishop hanging and attacks White's bishop instead.",
        },
    },
    {
        "id": "dutch", "name": "Dutch (Leningrad)", "group": "1.d4",
        "moves": "d4 f5 g3 Nf6 Bg2 g6 Nf3 Bg7 O-O O-O c4 d6 Nc3 Qe8 d5 a5",
        "about": "Black grabs the e4 square with the f-pawn and plays for a kingside attack. The "
                 "Leningrad version adds a King's Indian-style bishop on g7. Risky, but "
                 "uncompromising.",
        "notes": {
            "1...f5": "The Dutch: Black controls e4 from the side.",
            "3...g6": "The Leningrad: the bishop goes to g7.",
            "7...Qe8": "Prepares ...e5, and the queen can swing to f7 or h5.",
            "8.d5": "Gains space and makes ...e5 less attractive.",
            "8...a5": "Secures c5 for a knight.",
        },
    },
    {
        "id": "benoni", "name": "Modern Benoni", "group": "1.d4",
        "moves": "d4 Nf6 c4 c5 d5 e6 Nc3 exd5 cxd5 d6 e4 g6 Nf3 Bg7 Be2 O-O O-O Re8 Nd2 Na6 f3 Nc7",
        "about": "Black creates an unbalanced pawn structure straight away. White gets a central "
                 "pawn majority, while Black gets a queenside majority and active pieces. A "
                 "fighting choice when Black needs to win.",
        "notes": {
            "2...c5": "The Benoni: challenges d4 at once.",
            "3.d5": "White gains space instead of trading.",
            "4...exd5": "Creates a lopsided structure: White has more pawns in the centre, "
                        "Black has more on the queenside.",
            "9...Re8": "Puts pressure on e4.",
            "10.Nd2": "The knight heads for c4 to hit d6.",
            "11...Nc7": "Supports ...b5.",
        },
    },
    {
        "id": "benko", "name": "Benko Gambit", "group": "1.d4",
        "moves": "d4 Nf6 c4 c5 d5 b5 cxb5 a6 bxa6 g6 Nc3 Bxa6 e4 Bxf1 Kxf1 d6 Nf3 Bg7 g3 O-O Kg2 Nbd7",
        "about": "Black gives up a pawn for long-term pressure down the open a- and b-files. Black "
                 "doesn't attack the king, but squeezes White's queenside for the rest of the game.",
        "notes": {
            "3...b5": "The Benko: offers a pawn for queenside pressure.",
            "4...a6": "Offers another pawn to open the a- and b-files.",
            "7.e4": "White builds the centre, but will lose the right to castle.",
            "8.Kxf1": "White's king can't castle now.",
            "11.Kg2": "White's king tucks itself away by hand.",
        },
    },
    {
        "id": "catalan", "name": "Catalan", "group": "1.d4",
        "moves": "d4 Nf6 c4 e6 g3 d5 Bg2 Be7 Nf3 O-O O-O dxc4 Qc2 a6 Qxc4 b5 Qc2 Bb7 Bd2 Be4 Qc1",
        "about": "A mix of the Queen's Gambit and the Réti. The bishop on g2 presses down the long "
                 "diagonal toward Black's queenside. Even when Black grabs a pawn, White usually "
                 "wins it back and keeps a lasting edge.",
        "notes": {
            "3.g3": "The Catalan: the bishop on g2 will press the long diagonal.",
            "6...dxc4": "Black grabs the pawn, but White will win it back.",
            "7.Qc2": "Prepares to recapture on c4.",
            "8...b5": "Gains space with tempo.",
            "10...Be4": "Hits the queen and blocks the g2 bishop.",
        },
    },
    {
        "id": "trompowsky", "name": "Trompowsky Attack", "group": "1.d4",
        "moves": "d4 Nf6 Bg5 Ne4 Bf4 c5 f3 Qa5+ c3 Nf6 Nd2 cxd4 Nb3 Qb6 Qxd4 Nc6 Qxb6 axb6",
        "about": "White brings the bishop out on move two and threatens to double Black's pawns. "
                 "It sidesteps the big theory of the Indian defences and leads to unusual "
                 "positions early.",
        "notes": {
            "2.Bg5": "The Trompowsky: threatens Bxf6, doubling Black's pawns.",
            "2...Ne4": "Sidesteps and attacks the bishop.",
            "3...c5": "Strikes at d4.",
            "4.f3": "Kicks the knight off e4.",
            "4...Qa5+": "A check that forces White to block with c3.",
            "7.Nb3": "Hits the queen.",
            "9...axb6": "The queens are off. Black's doubled pawns are hard to attack.",
        },
    },
    # ------------------------------------------------ more flank openings
    {
        "id": "reti", "name": "Réti Opening", "group": "Other",
        "moves": "Nf3 d5 c4 e6 g3 Nf6 Bg2 Be7 O-O O-O b3 c5 Bb2 Nc6 e3 b6 Nc3 Bb7 cxd5 Nxd5",
        "about": "Named after Richard Réti, a pioneer of hypermodern chess. White controls the "
                 "centre with pieces and flank pawns instead of occupying it, and both bishops "
                 "aim at the middle from the sides.",
        "notes": {
            "1.Nf3": "The Réti: White controls the centre without committing pawns.",
            "2.c4": "Hits d5 from the side.",
            "3.g3": "The bishop goes to g2.",
            "6.b3": "Both bishops will aim at the centre from the flanks.",
            "10.cxd5": "Opens the c-file and the long diagonals.",
        },
    },
    {
        "id": "kia", "name": "King's Indian Attack", "group": "Other",
        "moves": "e4 e6 d3 d5 Nd2 Nf6 Ngf3 c5 g3 Nc6 Bg2 Be7 O-O O-O Re1 b5 e5 Nd7 Nf1 a5 h4 b4",
        "about": "A system rather than a sharp opening: White plays a King's Indian set-up with an "
                 "extra move. Bobby Fischer used it a lot. Here it's played against a French "
                 "set-up, where White attacks on the kingside and Black on the queenside.",
        "notes": {
            "2.d3": "The King's Indian Attack: a reversed King's Indian set-up.",
            "8.Re1": "Supports e4 and prepares e5.",
            "8...b5": "Black storms the queenside.",
            "9.e5": "Gains space and kicks the knight. White's attack will come on the kingside.",
            "10.Nf1": "The knight reroutes to h2 or e3 to join the attack.",
            "11.h4": "White's pawns march toward Black's king.",
        },
    },
    {
        "id": "bird", "name": "Bird's Opening", "group": "Other",
        "moves": "f4 d5 Nf3 Nf6 e3 g6 b3 Bg7 Bb2 O-O Be2 c5 O-O Nc6",
        "about": "Named after the 19th-century English player Henry Bird. White grabs e5 from the "
                 "side, like a Dutch Defence with colours reversed. Rare at top level, but a fun "
                 "surprise weapon.",
        "notes": {
            "1.f4": "Bird's Opening: controls e5 from the side.",
            "4.b3": "The bishop goes to b2 to aim at e5 and Black's king.",
            "6...c5": "Black takes space on the queenside.",
        },
    },
]

# ---------------------------------------------------------------- famous games
#
# Same format as the openings, plus who played, the year and the result.

GAME_LINES = [
    {
        "id": "opera", "name": "The Opera Game", "group": "Romantic era",
        "players": "Morphy vs. Duke of Brunswick & Count Isouard", "year": 1858, "result": "1-0",
        "moves": "e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 Qb3 Qe7 Nc3 c6 Bg5 b5 "
                 "Nxb5 cxb5 Bxb5+ Nbd7 O-O-O Rd8 Rxd7 Rxd7 Rd1 Qe6 Bxd7+ Nxd7 Qb8+ Nxb8 Rd8#",
        "about": "Paul Morphy played this in 1858 in a box at the Paris opera, against the Duke of "
                 "Brunswick and Count Isouard consulting together. It's the classic lesson in "
                 "development: Morphy gets every piece into the game while his opponents waste "
                 "time, then finishes with a queen sacrifice.",
        "notes": {
            "3...Bg4": "Pins the knight, but Black will soon have to give this bishop up for it.",
            "4...Bxf3": "Practically forced: 4...dxe5 loses a pawn after the queen trade and Nxe5.",
            "7.Qb3": "Lines up behind the bishop against f7, and attacks b7 at the same time.",
            "7...Qe7": "Defends f7, but now the queen blocks Black's own bishop on f8.",
            "8.Nc3": "Morphy ignores the b7 pawn and keeps developing.",
            "10.Nxb5": "A knight sacrifice to rip open lines toward Black's king.",
            "12.O-O-O": "Castles and puts the rook on the open d-file in one move.",
            "13.Rxd7": "Gives up the rook to keep the pressure on.",
            "16.Qb8+": "The queen sacrifice! The knight has to take it.",
            "17.Rd8#": "Checkmate. Morphy used only a few pieces, but every one of them was active.",
        },
    },
    {
        "id": "immortal", "name": "The Immortal Game", "group": "Romantic era",
        "players": "Anderssen vs. Kieseritzky", "year": 1851, "result": "1-0",
        "moves": "e4 e5 f4 exf4 Bc4 Qh4+ Kf1 b5 Bxb5 Nf6 Nf3 Qh6 d3 Nh5 Nh4 Qg5 Nf5 c6 g4 Nf6 "
                 "Rg1 cxb5 h4 Qg6 h5 Qg5 Qf3 Ng8 Bxf4 Qf6 Nc3 Bc5 Nd5 Qxb2 Bd6 Bxg1 e5 Qxa1+ "
                 "Ke2 Na6 Nxg7+ Kd8 Qf6+ Nxf6 Be7#",
        "about": "Adolf Anderssen vs. Lionel Kieseritzky, a casual game in London in 1851. "
                 "Anderssen gives up a bishop, both rooks and finally his queen, then checkmates "
                 "with his three remaining minor pieces. The most famous example of the romantic, "
                 "all-out attacking style.",
        "notes": {
            "2.f4": "The King's Gambit, the favourite opening of the era.",
            "3...Qh4+": "The check means White's king can no longer castle.",
            "4...b5": "Black gives up a pawn to pull White's bishop away.",
            "11.Rg1": "Anderssen lets Black take the bishop on b5 and keeps building the attack.",
            "17...Qxb2": "Black grabs a pawn and attacks the rook on a1.",
            "18.Bd6": "Anderssen offers both rooks! Bxg1 and Qxa1+ are coming, and he allows both.",
            "19.e5": "Cuts Black's queen off from defending the kingside.",
            "22.Qf6+": "The final sacrifice drags the g8 knight away from guarding e7.",
            "23.Be7#": "Checkmate with a bishop and two knights, while Black still has almost every piece.",
        },
    },
    {
        "id": "evergreen", "name": "The Evergreen Game", "group": "Romantic era",
        "players": "Anderssen vs. Dufresne", "year": 1852, "result": "1-0",
        "moves": "e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4 exd4 O-O d3 Qb3 Qf6 e5 Qg6 Re1 Nge7 "
                 "Ba3 b5 Qxb5 Rb8 Qa4 Bb6 Nbd2 Bb7 Ne4 Qf5 Bxd3 Qh5 Nf6+ gxf6 exf6 Rg8 Rad1 Qxf3 "
                 "Rxe7+ Nxe7 Qxd7+ Kxd7 Bf5+ Ke8 Bd7+ Kf8 Bxe7#",
        "about": "Anderssen again, a year after the Immortal Game, this time against Jean Dufresne "
                 "in Berlin. It opens with the Evans Gambit and ends with a rook sacrifice, a queen "
                 "sacrifice and a double check. Wilhelm Steinitz nicknamed it the 'evergreen' among "
                 "Anderssen's wins.",
        "notes": {
            "4.b4": "The Evans Gambit: a pawn sacrifice to gain time for c3 and d4.",
            "7.O-O": "White gives up another pawn to stay ahead in development.",
            "11.Ba3": "The bishop aims down the diagonal toward Black's king.",
            "17.Nf6+": "A knight sacrifice that rips open Black's kingside.",
            "19...Qxf3": "Black threatens Qxg2 checkmate, so White has to keep giving check.",
            "20.Rxe7+": "The finale starts with a rook sacrifice.",
            "21.Qxd7+": "Now the queen! The king has to take.",
            "22.Bf5+": "Double check: the bishop and the d1 rook both attack the king.",
            "24.Bxe7#": "Checkmate.",
        },
    },
    {
        "id": "century", "name": "The Game of the Century", "group": "Modern era",
        "players": "Byrne vs. Fischer", "year": 1956, "result": "0-1",
        "moves": "Nf3 Nf6 c4 g6 Nc3 Bg7 d4 O-O Bf4 d5 Qb3 dxc4 Qxc4 c6 e4 Nbd7 Rd1 Nb6 Qc5 Bg4 "
                 "Bg5 Na4 Qa3 Nxc3 bxc3 Nxe4 Bxe7 Qb6 Bc4 Nxc3 Bc5 Rfe8+ Kf1 Be6 Bxb6 Bxc4+ Kg1 "
                 "Ne2+ Kf1 Nxd4+ Kg1 Ne2+ Kf1 Nc3+ Kg1 axb6 Qb4 Ra4 Qxb6 Nxd1 h3 Rxa2 Kh2 Nxf2 "
                 "Re1 Rxe1 Qd8+ Bf8 Nxe1 Bd5 Nf3 Ne4 Qb8 b5 h4 h5 Ne5 Kg7 Kg1 Bc5+ Kf1 Ng3+ Ke1 "
                 "Bb4+ Kd1 Bb3+ Kc1 Ne2+ Kb1 Nc3+ Kc1 Rc2#",
        "about": "13-year-old Bobby Fischer, playing Black, beats Donald Byrne, one of the top "
                 "players in the US, in New York in 1956. On move 17 Fischer gives up his queen for "
                 "a crushing attack, collects a pile of White's pieces, and finishes with all his "
                 "pieces working together.",
        "notes": {
            "11...Na4": "A surprising knight jump that starts the fireworks.",
            "13...Nxe4": "Grabs the e4 pawn and opens lines toward White's king.",
            "14.Bxe7": "Attacks both the queen and the rook.",
            "17...Be6": "The famous queen sacrifice: Fischer leaves his queen on b6 to be taken.",
            "18.Bxb6": "Byrne takes the queen.",
            "18...Bxc4+": "Now a 'windmill' of checks begins.",
            "20...Nxd4+": "Every knight move is check, and Black collects material each time.",
            "25...Nxd1": "Black has won back far more than the queen, and White's king is stuck.",
            "41...Rc2#": "Checkmate, with knight, bishops and rook all working together.",
        },
    },
    {
        "id": "kasparov", "name": "Kasparov's Immortal", "group": "Modern era",
        "players": "Kasparov vs. Topalov", "year": 1999, "result": "1-0",
        "moves": "e4 d6 d4 Nf6 Nc3 g6 Be3 Bg7 Qd2 c6 f3 b5 Nge2 Nbd7 Bh6 Bxh6 Qxh6 Bb7 a3 e5 "
                 "O-O-O Qe7 Kb1 a6 Nc1 O-O-O Nb3 exd4 Rxd4 c5 Rd1 Nb6 g3 Kb8 Na5 Ba8 Bh3 d5 "
                 "Qf4+ Ka7 Rhe1 d4 Nd5 Nbxd5 exd5 Qd6 Rxd4 cxd4 Re7+ Kb6 Qxd4+ Kxa5 b4+ Ka4 Qc3 "
                 "Qxd5 Ra7 Bb7 Rxb7 Qc4 Qxf6 Kxa3 Qxa6+ Kxb4 c3+ Kxc3 Qa1+ Kd2 Qb2+ Kd1 Bf1 Rd2 "
                 "Rd7 Rxd7 Bxc4 bxc4 Qxh8 Rd3 Qa8 c3 Qa4+ Ke1 f4 f5 Kc1 Rd2 Qa7",
        "about": "Garry Kasparov vs. Veselin Topalov at Wijk aan Zee in 1999, often called "
                 "Kasparov's Immortal. Kasparov sacrifices a rook on move 24 and chases Black's "
                 "king all the way across the board to White's own back rank. Topalov resigned "
                 "after White's 44th move.",
        "notes": {
            "13...O-O-O": "Black castles queenside, right where White is going to attack.",
            "24.Rxd4": "The famous rook sacrifice, calculated many moves ahead.",
            "25.Re7+": "The king hunt begins.",
            "26...Kxa5": "Black's king is pulled forward, out of its shelter.",
            "27.b4+": "Another pawn given up to keep the king running.",
            "31...Kxa3": "The black king is now deep in White's half of the board.",
            "33.c3+": "One more pawn sacrifice to keep the king moving.",
            "35...Kd1": "Black's king has walked all the way to White's back rank.",
            "36.Bf1": "A quiet move in the middle of the chaos that sets up winning material.",
            "39.Qxh8": "White wins the rook, and the attack has paid off.",
            "44.Qa7": "Topalov resigned here, with White's extra material decisive.",
        },
    },
]

# ---------------------------------------------------------------- board logic

SKIP = {"...", "1-0", "0-1", "1/2-1/2", "*"}


def parse_line(name, text):
    """'1. e4 e5 2. Nf3 ...' -> (list of chess.Move, list of SAN strings)."""
    board = chess.Board()
    moves, san = [], []
    for token in text.replace(".", ". ").split():
        if token.rstrip(".").isdigit() or token in SKIP:
            continue
        try:
            move = board.parse_san(token)
        except ValueError:
            played = " ".join(san) or "(start)"
            raise SystemExit(f"{name}: '{token}' isn't a legal move after: {played}")
        san.append(board.san(move))
        moves.append(move)
        board.push(move)
    return moves, san


def note_ply(name, key, moves, san):
    """'3.Bc4' -> 4 (0-based ply index), checking the move matches."""
    number, sep, move = key.partition("...")
    if not sep:
        number, sep, move = key.partition(".")
    try:
        ply = (int(number) - 1) * 2 + (1 if sep == "..." else 0)
    except ValueError:
        raise SystemExit(f"{name}: can't read note key '{key}' (use '3.Bc4' or '3...Bc5')")
    if ply >= len(san):
        raise SystemExit(f"{name}: note '{key}' is past the end of the line")
    board = chess.Board()
    for m in moves[:ply]:
        board.push(m)
    try:
        same = board.parse_san(move.strip()) == moves[ply]   # accepts Ncb4 or Nb4, with/without +
    except ValueError:
        same = False
    if not same:
        actual = f"{number}{sep}{san[ply]}"
        raise SystemExit(f"{name}: note '{key}' doesn't match the move played there ({actual})")
    return ply


OPENINGS = {}
for _o in [dict(o, kind="opening") for o in OPENING_LINES] + \
          [dict(g, kind="game") for g in GAME_LINES]:
    if _o["id"] in OPENINGS:
        raise SystemExit(f"Two entries share the id '{_o['id']}'")
    _moves, _san = parse_line(_o["name"], _o["moves"])
    _notes = [""] * len(_san)
    for _key, _text in _o.get("notes", {}).items():
        _notes[note_ply(_o["name"], _key, _moves, _san)] = _text
    OPENINGS[_o["id"]] = {"id": _o["id"], "name": _o["name"], "group": _o["group"],
                          "about": _o.get("about", ""), "moves": _moves,
                          "san": _san, "notes": _notes, "kind": _o["kind"],
                          "players": _o.get("players", ""), "year": _o.get("year", ""),
                          "result": _o.get("result", "")}


def idx(square):
    """python-chess square (a1 = 0) -> panel index (a8 = 0)."""
    return (7 - chess.square_rank(square)) * 8 + chess.square_file(square)


def board_chars(board):
    """chess.Board -> list of 64 chars, index 0 = a8, '.' = empty."""
    out = ["."] * 64
    for square, piece in board.piece_map().items():
        out[idx(square)] = piece.symbol()
    return out


START = board_chars(chess.Board())

# ---------------------------------------------------------------- LEDs

def render(board, highlight=None):
    pixels = []
    for i, ch in enumerate(board):
        row, col = divmod(i, 8)
        if ch == ".":
            rgb = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
        else:
            rgb = PIECE_COLOURS[ch]
        pixels.append(scaled(rgb))
    if highlight:
        frm, to = highlight
        if board[frm] == ".":
            pixels[frm] = scaled(FLASH_FROM)
        pixels[to] = scaled(FLASH_TO)
    sense.set_pixels(pixels)


# ---------------------------------------------------------------- player

lock = threading.Lock()
job = 0                        # bumped on every new request to cancel the old one
state = {"opening": None, "ply": 0, "total": 0, "playing": False,
         "board": "".join(START), "last": None}


def set_state(**kw):
    with lock:
        state.update(kw)


def wait(seconds, my_job):
    """Sleep, but return False early if a newer request has taken over."""
    end = time.time() + seconds
    while time.time() < end:
        if job != my_job:
            return False
        time.sleep(0.03)
    return job == my_job


def play(opening_id, delay, my_job):
    op = OPENINGS[opening_id]
    set_state(opening=opening_id, ply=0, total=len(op["moves"]), playing=True,
              board="".join(START), last=None)
    render(START)
    if not wait(delay, my_job):
        return
    game = chess.Board()
    for i, move in enumerate(op["moves"]):
        game.push(move)
        board = board_chars(game)
        f, t = idx(move.from_square), idx(move.to_square)
        set_state(ply=i + 1, board="".join(board), last=[f, t])
        render(board, (f, t))
        if not wait(FLASH_SECONDS, my_job):
            return
        render(board)
        # linger a bit longer on moves that have a note, so there's time to read it
        pause = delay * (1.8 if op["notes"][i] else 1.0)
        if not wait(max(0.0, pause - FLASH_SECONDS), my_job):
            return
    set_state(playing=False)


def start_job(target, *args):
    global job
    with lock:
        job += 1
        my_job = job
    if target:
        threading.Thread(target=target, args=(*args, my_job), daemon=True).start()


# ---------------------------------------------------------------- web

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the terminal quiet

    def send(self, body, ctype="application/json", code=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self.send(PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/openings":
            public = [{k: v for k, v in o.items() if k != "moves"} for o in OPENINGS.values()]
            self.send(json.dumps(public))
        elif self.path == "/api/state":
            with lock:
                self.send(json.dumps(state))
        else:
            self.send('{"error":"not found"}', code=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}

        if self.path == "/api/play" and body.get("id") in OPENINGS:
            try:
                delay = min(5.0, max(0.4, float(body.get("delay", DEFAULT_DELAY))))
            except (TypeError, ValueError):
                delay = DEFAULT_DELAY
            start_job(play, body["id"], delay)
            self.send('{"ok":true}')
        elif self.path == "/api/stop":
            start_job(None)
            set_state(playing=False)
            self.send('{"ok":true}')
        elif self.path == "/api/clear":
            start_job(None)
            sense.clear()
            set_state(opening=None, ply=0, total=0, playing=False,
                      board="." * 64, last=None)
            self.send('{"ok":true}')
        else:
            self.send('{"error":"bad request"}', code=400)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pi Openings</title>
<style>
  :root { --bg:#14161a; --card:#1e2127; --line:#2c3038; --text:#e8e6e1; --muted:#9097a3;
          --white:#ffb847; --black:#5aa6ff; --accent:#f0c674; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; }
  main { max-width:1000px; margin:0 auto; padding:20px 16px 40px;
         display:grid; gap:24px; grid-template-columns:1fr 340px; }
  @media (max-width:780px) { main { grid-template-columns:1fr; } aside { order:-1; position:static; } }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:var(--muted); margin:0 0 18px; }
  h2 { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted);
       margin:18px 0 8px; }
  .tabs { display:flex; gap:6px; margin:6px 0 4px; }
  .tabs button { background:none; border:1px solid var(--line); padding:7px 14px; color:var(--muted); }
  .tabs button.on { background:var(--card); color:var(--text); border-color:var(--accent); }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:8px; }
  button { font:inherit; color:inherit; cursor:pointer; border-radius:10px; }
  .op { background:var(--card); border:1px solid var(--line); padding:12px; text-align:left; }
  .op:hover { border-color:#4a505c; }
  .op.active { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent) inset; }
  .op b { display:block; font-weight:600; }
  .op span { color:var(--muted); font-size:12px; }
  aside { position:sticky; top:16px; align-self:start; }
  .board { display:grid; grid-template-columns:repeat(8,1fr); aspect-ratio:1;
           border-radius:10px; overflow:hidden; border:1px solid var(--line); }
  .sq { display:flex; align-items:center; justify-content:center; font-size:min(7vw,30px); }
  .sq.l { background:#3a3326; } .sq.d { background:#0c0c0c; }
  .sq.from { background:#46463c; } .sq.to { outline:2px solid #fff; outline-offset:-2px; }
  .w { color:var(--white); } .k { color:var(--black); }
  .now { margin:12px 0 6px; font-weight:600; min-height:1.4em; }
  .moves { color:var(--muted); font-size:14px; min-height:1.4em; }
  .moves span { border-radius:4px; padding:0 2px; }
  .moves .has-note { border-bottom:1px dotted var(--muted); cursor:pointer; }
  .moves .cur { color:var(--text); background:#3a3f4a; }
  .note { margin-top:10px; padding:10px 12px; border-left:3px solid var(--accent);
          background:var(--card); border-radius:0 8px 8px 0; font-size:14px; min-height:2.6em; }
  .note:empty { display:none; }
  .note b { color:var(--accent); font-weight:600; margin-right:4px; }
  .about { color:var(--muted); font-size:14px; margin-top:12px; }
  .about:empty { display:none; }
  .controls { display:flex; gap:8px; margin-top:14px; }
  .controls button { flex:1; background:var(--card); border:1px solid var(--line); padding:9px; }
  label { display:block; margin-top:14px; color:var(--muted); font-size:13px; }
  input[type=range] { width:100%; accent-color:var(--accent); }
  .err { color:#ff7b72; font-size:13px; min-height:1.2em; margin-top:8px; }
</style>
</head>
<body>
<main>
  <section>
    <h1>Pi Openings</h1>
    <nav class="tabs">
      <button data-tab="opening" class="on">Openings</button>
      <button data-tab="game">Famous games</button>
    </nav>
    <p class="sub" id="sub">Tap an opening to play it on the Sense HAT.</p>
    <div id="tab-opening"></div>
    <div id="tab-game" hidden></div>
  </section>
  <aside>
    <div class="board" id="board"></div>
    <div class="now" id="now">Nothing playing</div>
    <div class="moves" id="moves"></div>
    <div class="note" id="note"></div>
    <div class="about" id="about"></div>
    <label>Speed: <span id="dval"></span> s per move
      <input type="range" id="delay" min="0.4" max="3" step="0.1" value="1.2"></label>
    <div class="controls">
      <button id="replay">Replay</button>
      <button id="stop">Stop</button>
      <button id="clear">Clear LEDs</button>
    </div>
    <div class="err" id="err"></div>
  </aside>
</main>
<script>
const GLYPH = {k:"♚",q:"♛",r:"♜",b:"♝",n:"♞",p:"♟"};
let openings = {}, current = null, lastPly = -1, pinned = null;
const $ = id => document.getElementById(id);
const delay = $("delay");
const showDelay = () => $("dval").textContent = (+delay.value).toFixed(1);
delay.oninput = showDelay; showDelay();

async function post(path, body) {
  try {
    const r = await fetch(path, {method:"POST", body: JSON.stringify(body || {})});
    if (!r.ok) throw new Error(r.status);
    $("err").textContent = "";
  } catch (e) { $("err").textContent = "Couldn't reach the Pi."; }
}
const play = id => { pinned = null; post("/api/play", {id, delay: +delay.value}); };
$("replay").onclick = () => current && play(current);
$("stop").onclick = () => post("/api/stop");
$("clear").onclick = () => post("/api/clear");

const moveLabel = i => `${Math.floor(i / 2) + 1}${i % 2 ? "..." : "."}`;

function showNote(o, i) {
  const n = $("note");
  n.innerHTML = "";
  if (!o || i < 0 || !o.notes[i]) return;
  const b = document.createElement("b");
  b.textContent = moveLabel(i) + o.san[i];
  n.append(b, o.notes[i]);
}

const SUB = {opening: "Tap an opening to play it on the Sense HAT.",
             game: "Tap a game to replay it move by move on the Sense HAT."};
function showTab(t) {
  document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  $("tab-opening").hidden = t !== "opening";
  $("tab-game").hidden = t !== "game";
  $("sub").textContent = SUB[t];
}
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => showTab(b.dataset.tab));

const RESULT = {"1-0": "White wins", "0-1": "Black wins", "1/2-1/2": "Draw"};

async function init() {
  const list = await (await fetch("/api/openings")).json();
  const groups = {};
  for (const o of list) { openings[o.id] = o; (groups[o.kind + "|" + o.group] ||= []).push(o); }
  for (const [key, ops] of Object.entries(groups)) {
    const [kind, g] = key.split("|");
    const box = $("tab-" + kind);
    const h = document.createElement("h2"); h.textContent = g; box.append(h);
    const grid = document.createElement("div"); grid.className = "grid";
    for (const o of ops) {
      const b = document.createElement("button");
      b.className = "op"; b.dataset.id = o.id;
      b.innerHTML = `<b></b><span></span>`;
      b.querySelector("b").textContent = o.name;
      const n = Math.ceil(o.san.length / 2) + " moves";
      b.querySelector("span").textContent = o.kind === "game"
        ? `${o.players} · ${o.year} · ${n}`
        : o.san.slice(0, 4).join(" ") + " …  · " + n;
      b.onclick = () => play(o.id);
      grid.append(b);
    }
    box.append(grid);
  }
  for (let i = 0; i < 64; i++) {
    const d = document.createElement("div");
    d.className = "sq " + (((i >> 3) + i) % 2 ? "d" : "l");
    $("board").append(d);
  }
  poll();
}

function draw(s) {
  const changed = s.opening !== current;
  current = s.opening;
  document.querySelectorAll(".op").forEach(b => b.classList.toggle("active", b.dataset.id === s.opening));
  const cells = $("board").children;
  for (let i = 0; i < 64; i++) {
    const ch = s.board[i], c = cells[i];
    c.textContent = ch === "." ? "" : GLYPH[ch.toLowerCase()];
    c.className = "sq " + (((i >> 3) + i) % 2 ? "d" : "l") +
      (ch === "." ? "" : ch === ch.toUpperCase() ? " w" : " k");
    if (s.last && i === s.last[0]) c.classList.add("from");
    if (s.last && i === s.last[1]) c.classList.add("to");
  }
  const o = openings[s.opening];
  const done = o && o.result ? `${o.result} · ${RESULT[o.result] || ""}` : "done";
  $("now").textContent = o ? `${o.name} — ${s.playing ? "move " + Math.ceil(s.ply / 2) + "/" + Math.ceil(s.total / 2) : done}` : "Nothing playing";
  if (changed) $("about").textContent = o ? o.about : "";

  // move list: dotted underline = has a note; tap to read it
  $("moves").innerHTML = "";
  if (o) o.san.forEach((m, i) => {
    if (i % 2 === 0) $("moves").append(`${i / 2 + 1}. `);
    const sp = document.createElement("span"); sp.textContent = m;
    if (o.notes[i]) { sp.className = "has-note"; sp.onclick = () => { pinned = i; showNote(o, i); }; }
    if (i === s.ply - 1) sp.classList.add("cur");
    $("moves").append(sp, " ");
  });

  // while playing, show the note for the latest move that has one
  if (s.ply !== lastPly || changed) {
    lastPly = s.ply;
    if (s.playing || pinned === null) {
      pinned = null;
      let i = s.ply - 1;
      while (o && i >= 0 && !o.notes[i]) i--;
      showNote(o, i);
    }
  }
}

async function poll() {
  try { draw(await (await fetch("/api/state")).json()); $("err").textContent = ""; }
  catch (e) { $("err").textContent = "Lost connection to the Pi."; }
  setTimeout(poll, 250);
}
init();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------- entry

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Open http://ryanpi.local:{PORT} on any device on the same network (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        start_job(None)
        sense.clear()
