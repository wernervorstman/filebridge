# Opdracht: FileBridge-card toevoegen aan portfolio.html (datalore.eu)

## Doel

Voeg op `portfolio.html` een vierde projectcard toe voor **FileBridge**, met drie downloadknoppen
(macOS, Windows, Linux) en een link naar de broncode. De card moet er precies zo uitzien als de
bestaande cards 01–03.

## Belangrijk: plaatsing (hier ging het eerder mis)

De projectcards zijn **broers van elkaar** binnen `<div class="container projects">`. Eerder is de
FileBridge-card per ongeluk **binnen** card 03 geplakt, waardoor hij als card-in-een-card werd
getoond. Dat mag niet.

- Zoek card 03: het `<article class="project">` met `<h2 id="project3_title">Twinfield → Power BI koppeling</h2>`.
- Plak de nieuwe card **direct na de afsluitende `</article>` van card 03**.
- Dat is dus vóór de `</div>` die de projectenlijst (`.projects`) afsluit, en vóór `</section>`.
- **Niet** plakken vóór de `</div></article>` van card 03, en niet in `.fields` van card 03.

Schematisch moet het zo worden:

```html
<div class="container projects">
  <article class="project"> …01… </article>
  <article class="project"> …02… </article>
  <article class="project"> …03… </article>
  <article class="project"> …04 FileBridge… </article>   <!-- nieuw, zelfde niveau -->
</div>
```

## 1. HTML van de card

Plak dit blok letterlijk op de plek die hierboven beschreven staat:

```html
      <article class="project">
        <div class="idx">04</div>
        <div>
          <span class="tag">Eigen project</span>
          <h2 id="project4_title">FileBridge</h2>
          <p id="project4_desc">Een eigen SFTP- en FTP-client, gebouwd omdat FileZilla net niet genoeg kon voor het dagelijkse websitebeheer. Links je eigen bestanden, rechts de server — maar met de handelingen die steeds terugkomen als één klik: alleen uploaden wat nog niet online staat, permissies selecteren en rechtzetten (ook alleen op bestanden die nu bijvoorbeeld 0777 zijn), vaste permissies na elke upload, en een zip uploaden en direct op de server uitpakken.</p>
          <p id="project4_desc2">Verder: mappen vergelijken en synchroniseren, updates uitrollen met automatische back-up, een Site Manager in FileZilla-stijl, wachtwoorden in de sleutelhanger van het systeem en uitbreidbaar met eigen plugins. Draait als eigen app op macOS, Windows en Linux.</p>
          <div class="fields">
            <span><b>Protocollen:</b> SFTP · FTP · FTP over TLS</span>
            <span><b>Platforms:</b> macOS · Windows · Linux</span>
            <span><b>Techniek:</b> Python · HTML/CSS/JS</span>
          </div>
          <div class="downloads">
            <a class="link" href="https://github.com/wernervorstman/filebridge/releases/latest/download/FileBridge-macOS.dmg">Download voor macOS <span class="arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M6 13l6 6 6-6"/></svg></span></a>
            <a class="link" href="https://github.com/wernervorstman/filebridge/releases/latest/download/FileBridge.exe">Download voor Windows <span class="arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M6 13l6 6 6-6"/></svg></span></a>
            <a class="link" href="https://github.com/wernervorstman/filebridge/releases/latest/download/FileBridge-Linux.tar.gz">Download voor Linux <span class="arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M6 13l6 6 6-6"/></svg></span></a>
          </div>
          <p class="note">Gratis en open source (MIT) · <a href="https://github.com/wernervorstman/filebridge" target="_blank" rel="noopener">broncode op GitHub</a>. De apps zijn digitaal ondertekend: Windows door DataLore, macOS met een Apple Developer ID en gecontroleerd door Apple, zodat ze zonder waarschuwing over een onbekende maker openen. <a href="https://github.com/wernervorstman/filebridge/blob/main/docs/INSTALL.md" target="_blank" rel="noopener">Installatie-instructies</a> (Engels) voor macOS, Windows en Linux.</p>
        </div>
      </article>
```

## 2. CSS toevoegen

In de `<style>` van `portfolio.html` staat al de opmaak voor `.project a.link`. Voeg **direct na**
de regel `.project a.link .arrow svg { width: 11px; height: 11px; }` deze vier regels toe:

```css
  .project .downloads { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
  .project .downloads a.link { margin-top: 0; }
  .project p.note { font-size: 0.8rem; margin-top: 14px; max-width: 70ch; }
  .project p.note a { color: var(--green-deep); font-weight: 600; }
```

De knoppen gebruiken zo dezelfde pil-stijl als de bestaande link "Bekijk op wernervorstman.nl" bij
card 01, maar met een pijl naar beneden (download) in plaats van naar rechts.

## 3. Optioneel: intro en meta-omschrijving

- In `<section class="intro">`: vervang
  `…educatieve vogelgidsen en een boekhoudkoppeling die maanden werk uit een rapportageproces haalt`
  door
  `…educatieve vogelgidsen, een boekhoudkoppeling die maanden werk uit een rapportageproces haalt en een eigen bestandsbeheerder voor websites`.
- In `<meta name="description">`: vervang
  `tot vogelgidsen en een Twinfield/Power BI-koppeling.`
  door
  `tot vogelgidsen, een Twinfield/Power BI-koppeling en FileBridge.`

## 4. Optioneel: bewerkbaar via het admin-paneel (content.json)

De teksten van card 01–03 worden bij het laden overschreven vanuit `content.json` (script onderaan
de pagina, met `setText('project1_title', …)` enzovoort). Card 04 werkt ook zonder deze stap: dan
blijft de tekst uit de HTML staan. Moet card 04 via het admin-paneel bewerkbaar zijn:

1. Voeg in het script, na `setText('project3_desc2', c.project3_desc2);`, toe:
   ```js
   setText('project4_title', c.project4_title);
   setText('project4_desc', c.project4_desc);
   setText('project4_desc2', c.project4_desc2);
   ```
2. Voeg de sleutels `project4_title`, `project4_desc` en `project4_desc2` toe aan `content.json`,
   met dezelfde teksten als in de HTML.
3. Pas `admin.php` aan zodat die drie velden daar ook te bewerken zijn.

Controleer eerst of `setText` niets doet bij een lege of ontbrekende waarde. Anders zou de card leeg
worden zolang `content.json` die sleutels nog niet heeft.

## Wat je niet moet doen

- De downloadlinks **niet** veranderen naar een vast versienummer. `releases/latest/download/…`
  wijst altijd naar de nieuwste versie.
- Niet schrijven dat de app "ondertekend", "veilig gecertificeerd" of "in de App Store" is. Dat is
  niet zo.
- De card niet nesten in card 03 (zie boven).
- Geen andere cards of teksten wijzigen.

## Controle na afloop

- [ ] `document.querySelectorAll('.projects > article').length` is **4**.
- [ ] `document.querySelectorAll('article article').length` is **0** (geen card in een card).
- [ ] Card 04 staat onder card 03, even breed, met "04" in groen en de tag "EIGEN PROJECT".
- [ ] De drie knoppen staan naast elkaar (op mobiel onder elkaar), in de stijl van de knop bij card 01.
- [ ] Elke downloadlink geeft een download, geen 404:
  - https://github.com/wernervorstman/filebridge/releases/latest/download/FileBridge-macOS.dmg
  - https://github.com/wernervorstman/filebridge/releases/latest/download/FileBridge.exe
  - https://github.com/wernervorstman/filebridge/releases/latest/download/FileBridge-Linux.tar.gz
- [ ] "broncode op GitHub" opent https://github.com/wernervorstman/filebridge in een nieuw tabblad.

## Achtergrond (ter info)

- FileBridge is gemaakt door DataLore, staat op GitHub onder `wernervorstman/filebridge` en valt
  onder de MIT-licentie.
- Elke nieuwe versie (tag `vX.Y.Z`) wordt automatisch gebouwd voor de drie systemen. De links
  hierboven wijzen altijd naar de nieuwste release.
- Er staat al een werkende versie van deze wijziging in de lokale
  `~/Documents/Websites/Datalore.eu/portfolio.html`. Dit document beschrijft hoe je dezelfde wijziging
  opnieuw doet, bijvoorbeeld op de online versie.
