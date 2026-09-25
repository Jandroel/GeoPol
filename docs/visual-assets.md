# Recursos visuales de GeoPol

## Fondos de Vista general por tema

Los dos PNG fueron aportados por el usuario el 25 de septiembre de 2026 para
utilizarlos como fondos de Vista general. Se incorporan como archivos locales,
sin edición, recoloreado ni regeneración; cada tema utiliza su imagen original.

| Tema   | Archivo de la aplicación                         | Archivo aportado                                           | Dimensiones   | Tamaño          |
| ------ | ------------------------------------------------ | ---------------------------------------------------------- | ------------- | --------------- |
| Claro  | `frontend/public/images/overview-peru-light.png` | `codex-clipboard-03075cba-7163-4a39-a4c7-32dfe2b802a2.png` | 1672 × 941 px | 2 512 126 bytes |
| Oscuro | `frontend/public/images/overview-peru-dark.png`  | `codex-clipboard-8eec1df8-759b-4d33-b61c-52c97fbb8caa.png` | 1672 × 941 px | 2 426 357 bytes |

Huella SHA-256 de los originales, para comprobar que la incorporación conserva
los mismos archivos:

- Claro: `dc9d833d1c576fdea5e1b75e5e56a6481dc913fe65028110fb2578a53f5827e7`.
- Oscuro: `3597c3748668c44a5123bde330dc330d437e1f53eb4a0b1bcb32266eeb32d1f5`.

### Aplicación

- Las URL locales son `/images/overview-peru-light.png` y
  `/images/overview-peru-dark.png`; la elección sigue el tema de la aplicación.
- Uso decorativo exclusivo de Vista general. La navegación, los formularios y
  las demás páginas conservan sus superficies y tokens propios.
- El ajuste de tamaño y posición corresponde al diseño responsive y no modifica
  los archivos. El fondo no recibe interacción ni sustituye contenido accesible.
- Los relieves, luces y trazos pertenecen a la imagen decorativa; no representan
  resultados del procesamiento ni cartografía operativa. El módulo de Estadística
  sigue utilizando las geometrías reales de los resultados por separado.
- Se sirven desde la aplicación, sin cargar mapas ni recursos de proveedores
  externos.

## Ilustración anterior de Perú

Registro de la ilustración utilizada antes de incorporar los fondos por tema.

- Archivo: `frontend/public/images/peru-geospatial.png`.
- Generación: herramienta integrada ImageGen, 25 de septiembre de 2026.
- Uso anterior: ilustración decorativa de Vista general, con fondo transparente.
- Los colores, luces y líneas forman parte de la ilustración. No representan
  resultados, frecuencias delictivas ni cartografía operativa. El módulo de
  Estadística utiliza las geometrías reales de los resultados por separado.
- Ambos temas utilizaban el mismo PNG con superficies CSS adaptadas y canal alfa.
  Los fondos aportados por el usuario sustituyen esta aplicación en Vista general.

### Prompt final

```text
Use case: productivity-visual. Asset type: decorative raster map illustration for the GeoPol INEI web dashboard, isolated with a genuinely transparent background so CSS can place it on either white or navy. Create one clean, premium cartographic illustration of Peru: geographically recognizable complete silhouette of Peru with north at top, long Pacific coastline on the southwest/left, Amazon basin in northeast, borders and proportions faithful to Peru. Top-down orthographic view, never isometric. Very fine muted blue and teal terrain relief, subtle pale gold internal regional boundary-like linework and delicate interconnected amber lights mostly following the coastal corridor with a brighter warm cluster in central coast, matching the visual language of a geospatial intelligence dashboard. Lights are abstract decorative network accents, not labeled data. Full country visible centered with modest padding, portrait aspect ratio about 3:4. Crisp highly detailed but elegant, luminous without excessive glow. The land should be mid-tone teal-blue with some muted green terrain, suitable on both light and dark backgrounds. Transparent outside the country, no rectangular ocean/background. No text, no letters, no numbers, no legends, no logos, no UI, no dashboard cards, no watermark, no compass, no scales, no labels, no neighboring country names. All illustration content must remain inside the Peru silhouette, clear natural coastline and border. Render as clean usable website art, not a screenshot.
```
