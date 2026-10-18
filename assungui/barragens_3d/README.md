# PCHs do Complexo Assungui em 3D (Google Earth)

`Complexo_Assungui_PCHs_3D.kmz` abre no Google Earth Pro. Ele mostra as 5 PCHs (2B, 2C, 2D, 2E e 2F) com:

- **Barragem 3D**: modelo sólido (COLLADA, em `modelos/`), com sombreamento pela luz do Google Earth. A barragem de CCR tem paramento liso e o vertedouro de soleira livre tem degraus;
- **Casa de força**: bloco com telhado no pé da barragem;
- **Lâmina d'água 3D (NA)**: lago plano na cota do NA;
- **Área alagada** (azul) e **APP** (verde): mesmo estilo dos KMZ de reservatório.

Para cada PCH, dê duplo clique na pasta ou no ícone: a câmera vai para uma vista oblíqua a partir de jusante. Antes do print para o PowerPoint, ative **Visualizar → Exibir relevo**. Para a vista ficar mais limpa, desligue a camada "Área alagada".

## Dados usados

| PCH | NA (m) | Crista (m) | Vertedouro | Ajuste vertical |
|---|---|---|---|---|
| 2B | 370,0 ¹ | 374,5 ² | 130 m | +9 m |
| 2C | 450,0 | 456,5 ³ | 80 m | +13 m |
| 2D | 484,0 | 488,7 | 80 m | +16 m |
| 2E | 502,0 | 506,4 | 80 m | +20 m |
| 2F | 534,5 | 538,5 ² | 83 m | +20 m |

Fontes: Fichas-Resumo e Fichas Técnicas do Projeto Básico, habilitação EPE (NA da 2F) e os KMZ de reservatório e arranjo da pasta `_ORGANIZADO`.

1. A 2B usa o contorno do reservatório do arranjo do PRBA, desenhado na cota 370. A Ficha-Resumo GeoEnergy (2016) indica NA 374.
2. Crista estimada (NA máximo maximorum + ~1,3 m), porque não consta na ficha.
3. Cota das estruturas de concreto no KMZ do reestudo da 2C.

**Ajuste vertical:** o relevo do Google Earth (SRTM) fica 10–25 m acima do terreno real no fundo desses vales estreitos. Com as cotas reais, as barragens ficariam enterradas. Por isso a geometria é elevada pelo valor da tabela, calibrado na margem de cada reservatório. As cotas reais aparecem no balão de cada PCH. O modelo é ilustrativo e não substitui os desenhos do projeto.

## Regerar

`python gerar_kmz_3d.py <pasta_kml> saida.kmz` (requer `pyproj` e `shapely`). A pasta deve conter os `doc.kml` extraídos dos KMZ de origem, com os nomes listados em `PCHS[...]["fonte"]`.
