# The printed binder

The computer can fail. Print these and keep them in a binder next to it, with colored tabs. Reprint after changes.

The website's **Binder** page (`/binder`, linked from **Print**) is the full list to print: nine 1-inch binders of similar things (up to about 250 sheets each): first aid on its own as Emergency medical, everything else medical in one Long-term medical binder, and the area maps and the route maps kept apart, with the right chapters and pages already picked and every map in `family/maps`. It comes from the `binders:` section of `library.yaml`. Each binder's list starts with its cover, one page for the clear front sleeve: the binder's number, colour, what it's for and what's in it. A cover is made again whenever its binder's list changes, and then shows as **print again**. This file covers what the list can't: encyclopedia articles and things kept in the vault. The repo's own guides (this one included) are the list's "This server" binder, except the two radio guides, which are in "Radio how-to".

The links work from any browser on the home network or the hotspot (on the hotspot, `library.lan` works in place of `homestead.local`). There are two kinds of source:

- **Documents** in `/srv/core/docs/<topic>/`. Print them from the website's **Print** page: pick the chapters or pages, then send them to the printer or open them as one PDF.
- **Encyclopedias** in `/srv/core/zim/`. An encyclopedia holds a whole collection, so the links below are searches on the website. Open the article you want and print it from the browser.

Items marked **(get by hand)** aren't downloaded automatically: the website's **Status** page lists them, and the library manager's **Add → a file from this computer** puts them in the right place. Save them under the filename shown, and the link will work. Books published chapter by chapter link to their folder.

## RED: EMERGENCY MEDICAL

| Item | Link | On disk |
|---|---|---|
| Stop the Bleed: Save a Life booklet | http://homestead.local/read/medical/stop-the-bleed-save-a-life-booklet-american-college-of-surgeons.pdf | `/srv/core/docs/medical/stop-the-bleed-save-a-life-booklet-american-college-of-surgeons.pdf` |
| TCCC and first aid (ATP 4-02.11, US Army) | http://homestead.local/read/medical/atp-4-02-11-casualty-response-tactical-combat-casualty-care-and-first.pdf | `/srv/core/docs/medical/atp-4-02-11-casualty-response-tactical-combat-casualty-care-and-first.pdf` |
| Emergency War Surgery (all chapters) | http://homestead.local/book/emergency-war-surgery-5th-us-revision-borden-institute | `/srv/core/docs/medical/emergency-war-surgery-5th-us-revision-borden-institute/` |
| Bleeding control / tourniquet | http://homestead.local/search?q=tourniquet | `/srv/core/zim/` (zimgit-medicine, WikEM, WikiMed) |
| CPR: adult, child, infant | http://homestead.local/search?q=cardiopulmonary+resuscitation | `/srv/core/zim/` |
| Choking | http://homestead.local/search?q=choking+first+aid | `/srv/core/zim/` |
| Burns | http://homestead.local/search?q=burn+treatment | `/srv/core/zim/` |
| Fractures and splints | http://homestead.local/search?q=splint+fracture | `/srv/core/zim/` |
| Shock | http://homestead.local/search?q=shock+treatment | `/srv/core/zim/` |
| Hypothermia / heat illness | http://homestead.local/search?q=hypothermia | `/srv/core/zim/` |
| Wound care and infection signs | http://homestead.local/search?q=wound+infection | `/srv/core/zim/` |

## RED: LONG-TERM MEDICAL

Sickness and medicines, childbirth, children and teeth, and stress and coping.

| Item | Link | On disk |
|---|---|---|
| Where There Is No Doctor (chapter PDFs) | http://homestead.local/book/where-there-is-no-doctor-hesperian | `/srv/core/docs/medical/where-there-is-no-doctor-hesperian/` |
| Where There Is No Dentist (chapter PDFs) | http://homestead.local/book/where-there-is-no-dentist-hesperian | `/srv/core/docs/medical/where-there-is-no-dentist-hesperian/` |
| Where Women Have No Doctor (chapter PDFs) | http://homestead.local/book/where-women-have-no-doctor-hesperian | `/srv/core/docs/medical/where-women-have-no-doctor-hesperian/` |
| A Book for Midwives (chapter PDFs) | http://homestead.local/book/a-book-for-midwives-hesperian | `/srv/core/docs/medical/a-book-for-midwives-hesperian/` |
| Oral rehydration | http://homestead.local/search?q=oral+rehydration+solution | `/srv/core/zim/` |
| Childbirth basics | http://homestead.local/search?q=childbirth | `/srv/core/zim/` |
| Drug doses and interactions | http://homestead.local/search?q=paracetamol (change the drug name) | `/srv/core/zim/` (NHS medicines A-Z) |
| Family medication list and allergies | write it and keep it in the vault: http://homestead.local:7092 | vault (Paperless) |
| Doing What Matters in Times of Stress (WHO) | http://homestead.local/read/mind/doing-what-matters-in-times-of-stress-an-illustrated-guide-who-2020.pdf | `/srv/core/docs/mind/doing-what-matters-in-times-of-stress-an-illustrated-guide-who-2020.pdf` |
| Managing stress after a disaster (SAMHSA tip sheet) | http://homestead.local/read/mind/tips-for-survivors-of-a-disaster-managing-stress-samhsa.pdf | `/srv/core/docs/mind/tips-for-survivors-of-a-disaster-managing-stress-samhsa.pdf` |
| Helping infants and toddlers after a disaster | http://homestead.local/read/mind/parent-tips-infants-and-toddlers-after-disasters-nctsn.pdf | `/srv/core/docs/mind/parent-tips-infants-and-toddlers-after-disasters-nctsn.pdf` |
| Helping preschool children after a disaster | http://homestead.local/read/mind/parent-tips-preschool-age-children-after-disasters-nctsn.pdf | `/srv/core/docs/mind/parent-tips-preschool-age-children-after-disasters-nctsn.pdf` |
| Helping school-age children after a disaster | http://homestead.local/read/mind/parent-tips-school-age-children-after-disasters-nctsn.pdf | `/srv/core/docs/mind/parent-tips-school-age-children-after-disasters-nctsn.pdf` |
| Helping teenagers after a disaster | http://homestead.local/read/mind/parent-tips-adolescents-after-disasters-nctsn.pdf | `/srv/core/docs/mind/parent-tips-adolescents-after-disasters-nctsn.pdf` |
| Psychological first aid: what to say and do | http://homestead.local/search?q=psychological+first+aid | `/srv/core/docs/mind/` |

## BLUE: WATER

| Item | Link | On disk |
|---|---|---|
| Boiling and bleach doses | http://homestead.local/search?q=bleach+water+disinfection | `/srv/core/zim/` (zimgit-water, CDC) |
| SODIS (solar disinfection) | http://homestead.local/search?q=SODIS | `/srv/core/zim/` |
| Filter maintenance | http://homestead.local/search?q=water+filter | `/srv/core/zim/` |
| Water storage and rotation (FEMA *Are You Ready?*) | http://homestead.local/read/survival/are-you-ready-fema-citizen-preparedness.pdf | `/srv/core/docs/survival/are-you-ready-fema-citizen-preparedness.pdf` |

## GREEN: FOOD

| Item | Link | On disk |
|---|---|---|
| USDA Complete Guide to Home Canning (8 parts) | http://homestead.local/book/usda-complete-guide-to-home-canning-2015 | `/srv/core/docs/food/usda-complete-guide-to-home-canning-2015/` |
| Canning times for your altitude | http://homestead.local/search?q=canning+altitude | `/srv/core/zim/` (USDA 2015, food preparation) |
| Botulism warning signs | http://homestead.local/search?q=botulism | `/srv/core/zim/` |
| Vegetable planting chart (UMass Extension, Massachusetts) | http://homestead.local/read/food/umass-extension-vegetable-planting-chart-massachusetts.pdf | `/srv/core/docs/food/umass-extension-vegetable-planting-chart-massachusetts.pdf` |
| Where There Is No Animal Doctor (get by hand) | http://homestead.local/t/food (once added) | `/srv/core/docs/food/` |
| Livestock and vet care | http://homestead.local/search?q=livestock | `/srv/core/zim/` (WikiVet) |
| Food storage rotation list | http://homestead.local:7008/stockoverview (print the page) | Grocy's database |

## BLACK: SECURITY

| Item | Link | On disk |
|---|---|---|
| FM 21-76 Survival | http://homestead.local/search?q=FM+21-76 | `/srv/core/zim/` (Army publications) |
| Ranger Handbook (TC 3-21.76) | http://homestead.local/search?q=TC+3-21.76 | `/srv/core/zim/` |
| Rifle marksmanship (TC 3-22.9) | http://homestead.local/search?q=TC+3-22.9 | `/srv/core/zim/` |
| Physical security (FM 3-19.30) | http://homestead.local/search?q=FM+3-19.30 | `/srv/core/zim/` |
| CBRN (FM 3-11) | http://homestead.local/search?q=FM+3-11 | `/srv/core/zim/` |
| Nuclear War Survival Skills | http://homestead.local/read/survival/nuclear-war-survival-skills-kearny.pdf | `/srv/core/docs/survival/nuclear-war-survival-skills-kearny.pdf` |
| Defensible space against wildfire (FEMA) | http://homestead.local/read/security/defensible-space-around-your-home-against-wildfire-fema.pdf | `/srv/core/docs/security/defensible-space-around-your-home-against-wildfire-fema.pdf` |
| CERT Basic Training manual | http://homestead.local/read/survival/cert-basic-training-participant-manual-fema-2019.pdf | `/srv/core/docs/survival/cert-basic-training-participant-manual-fema-2019.pdf` |
| Firearm safety rules and manuals for your guns and gear (get by hand: manufacturers) | http://homestead.local/t/security | `/srv/core/docs/security/` |
| Area maps with routes marked | http://homestead.local/maps (find the place, **Print this view**, then mark by hand) | `/srv/core/maps/` |
| County topo maps (get by hand: ngmdb.usgs.gov/topoview) | http://homestead.local/t/survival | `/srv/core/docs/survival/` |
| Household watch roster, rally points | your plan; keep it in the vault: http://homestead.local:7092 | vault (Paperless) |

## PURPLE: RADIO HOW-TO

The Binder page's Radio how-to list has the band chart, the frequency, operating, antenna and message pages, and the radio guides. Add by hand:

| Item | Link | On disk |
|---|---|---|
| Local repeater list, ARES/RACES plan (get by hand: your county ARES, RepeaterBook) | http://homestead.local/t/comms | `/srv/core/docs/comms/` |
| Our frequencies and channels (family, neighbors, repeaters) | write it and keep it in the vault: http://homestead.local:7092 | vault (Paperless) |

## WHITE: THIS COMPUTER

| Item | Link | On disk |
|---|---|---|
| Backup and restore | http://homestead.local/t/reference (Backup and restore guide), or binder "This server" | `/srv/core/docs/reference/server/` |
| Grid-down runbook | http://homestead.local/t/reference (Grid-down runbook) | `/srv/core/docs/reference/server/` |
| Power | http://homestead.local/t/reference (Power and batteries) | `/srv/core/docs/reference/server/` |
| WiFi sign with QR code | http://homestead.local/share/print/wifi-sign.html | `/srv/core/share/print/wifi-sign.html` |

The guides in this repo's `docs/` are made into PDFs on the server each time `bootstrap.sh` runs (`sudo homestead guides` makes them again by hand), so the website shows them on the Reference shelf and the Print page prints them.

## Sealed envelope (not in the binder)

Root password, dennis password, admin web password, borg passphrase, vault passphrase, BIOS password, Paperless admin. Keep a copy with BACKUP-B.
