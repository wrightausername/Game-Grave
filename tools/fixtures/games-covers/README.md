These two public game images supplement the owner's unchanged reference crops
in the disposable Games UI test. They are test inputs, not the owner's library
and not shipped app assets. The production resolver downloads matching artwork
on its worker; this fixture keeps repeated UI tests deterministic and offline.

- Assassin's Creed Odyssey: Steam app 812140 library image,
  https://cdn.cloudflare.steamstatic.com/steam/apps/812140/library_600x900.jpg
- Valorant: the exact Valorant Wikipedia page's public thumbnail, obtained from
  https://en.wikipedia.org/w/api.php?action=query&format=json&titles=Valorant&prop=pageimages&piprop=thumbnail&pithumbsize=600

Retrieved November 7, 2026 (America/New_York). Image rights remain with their owners.
