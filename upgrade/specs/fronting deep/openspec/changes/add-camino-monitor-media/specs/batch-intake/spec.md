# batch-intake

## ADDED Requirements

### Requirement: Carga de archivo CSV
La pantalla de inicio SHALL permitir cargar un archivo CSV con el botón "Elegir archivo CSV" o arrastrándolo sobre la zona de carga, y SHALL aceptar solo archivos con extensión `.csv` y tamaño menor o igual al máximo configurado (50 MB por defecto).

#### Scenario: CSV válido
- **WHEN** el usuario elige o suelta `catalogo_verano.csv` de 2 MB
- **THEN** la tarjeta "Lote a procesar" muestra el nombre, "Archivo CSV" y el tamaño
- **AND** el botón "Iniciar procesamiento" se habilita

#### Scenario: Archivo con otra extensión
- **WHEN** el usuario suelta `catalogo.xlsx`
- **THEN** se muestra el aviso "El archivo tiene que ser un .csv (foto + datos de cada prenda)."
- **AND** el botón "Iniciar procesamiento" sigue deshabilitado

#### Scenario: Archivo demasiado grande
- **WHEN** el usuario elige un CSV de 80 MB y el máximo es 50 MB
- **THEN** se muestra el aviso "El archivo supera el máximo de 50 MB."
- **AND** no se envía nada al servidor

#### Scenario: Resaltado al arrastrar
- **WHEN** el usuario arrastra un archivo sobre la zona de carga
- **THEN** el borde punteado y el fondo cambian al color de Fase 2 hasta que suelta o sale de la zona

### Requirement: Carga de carpeta
La pantalla de inicio SHALL permitir elegir una carpeta con "Elegir carpeta" o arrastrándola, SHALL exigir exactamente un archivo `.csv` dentro, y SHALL contar las imágenes `jpg`, `jpeg`, `png` y `webp` que contenga.

#### Scenario: Carpeta con CSV y fotos
- **WHEN** el usuario elige la carpeta `verano_2026` con `catalogo.csv` y 1.200 fotos
- **THEN** la tarjeta muestra "verano_2026", "Carpeta · catalogo.csv · 1.200 fotos" y el ícono de carpeta

#### Scenario: Carpeta sin CSV
- **WHEN** la carpeta elegida no contiene ningún `.csv`
- **THEN** se muestra el aviso "La carpeta no tiene ningún archivo .csv."

#### Scenario: Carpeta con más de un CSV
- **WHEN** la carpeta contiene `a.csv` y `b.csv`
- **THEN** se muestra el aviso "La carpeta tiene más de un .csv. Dejá uno solo por lote."

### Requirement: Modo prueba
La pantalla de inicio SHALL ofrecer la casilla "Modo prueba" (desmarcada por defecto) y SHALL enviar `dry_run=true` al iniciar cuando está marcada.

#### Scenario: Iniciar en modo prueba
- **WHEN** el usuario marca "Modo prueba" e inicia el lote
- **THEN** la solicitud de creación incluye `dry_run=true`
- **AND** el monitor muestra el chip "Modo prueba" y el banner amarillo correspondiente

### Requirement: Inicio idempotente del lote
El botón "Iniciar procesamiento" SHALL estar deshabilitado hasta que haya un archivo o carpeta válidos, SHALL enviar un `Idempotency-Key` estable por selección y, al recibir el `batch_id`, SHALL navegar a `/lotes/{batch_id}`.

#### Scenario: Doble clic
- **WHEN** el usuario hace doble clic en "Iniciar procesamiento"
- **THEN** el servidor crea un solo lote y ambas respuestas devuelven el mismo `batch_id`

#### Scenario: Error del servidor al crear
- **WHEN** `POST /batches` responde 5xx
- **THEN** se muestra "No pudimos iniciar el lote. Probá de nuevo." y el archivo sigue cargado

### Requirement: Subida de fotos de carpeta con progreso
Cuando la carga es una carpeta con imágenes, el sistema SHALL subirlas antes de crear el lote, con como máximo 6 subidas simultáneas y hasta 3 reintentos por archivo, mostrando el progreso "Subiendo fotos X de Y", y SHALL crear el lote solo cuando todas se subieron.

#### Scenario: Subida de 1.200 fotos
- **WHEN** el usuario inicia con una carpeta de 1.200 fotos
- **THEN** el botón muestra "Subiendo fotos 0 de 1.200" y avanza hasta "1.200 de 1.200"
- **AND** recién entonces se crea el lote y se navega al monitor

#### Scenario: Una foto falla definitivamente
- **WHEN** una foto falla 3 veces
- **THEN** se informa "No se pudo subir 1 foto: nombre.jpg" con las opciones "Reintentar" y "Iniciar igual"
- **AND** con "Iniciar igual" esa prenda terminará como `photo_unavailable` en la etapa 2.2

### Requirement: Validación de estructura solo en el servidor
El cliente MUST NOT validar columnas, filas ni códigos repetidos del CSV. Esa validación SHALL ocurrir en la etapa 1.2 del pipeline y verse en el monitor.

#### Scenario: CSV con SKU repetido
- **WHEN** el usuario inicia un CSV con un código de producto repetido
- **THEN** el lote se crea y el monitor muestra el corte en el nodo "Archivo recibido y validado"
