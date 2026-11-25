# CodeGuard-Py
### Detector de Plagio con Semántica Ligera y Manipulación Automática de Código

**Tematica:** Lenguajes de Programación  
**Tecnologías:** Python 3, ANTLR v4 (grammars-v4 Python3) y Streamlit.

---

## 1. Descripción del proyecto

CodeGuard-Py es una herramienta de análisis estático y manipulación automática de código fuente en Python 3, desarrollada mediante ANTLR v4.

A partir del recorrido del árbol sintáctico (*ParseTreeListener*), el sistema combina el análisis estructural con un nivel de semántica ligera para identificar similitudes entre implementaciones de código, incluso cuando estas presentan modificaciones en sus identificadores o contienen código innecesario.

Entre sus principales funcionalidades se encuentran:

- **Tabla de símbolos local por función:** clasifica los identificadores según su rol semántico, utilizando identificadores normalizados como `PARAM_i` para parámetros y `LOCAL_i` para variables locales. También conserva la identidad de las funciones nativas de Python (`len`, `range`, `print`, entre otras).
- **Rastreo Def-Use y detección de código muerto:** contabiliza las definiciones y los usos de las variables locales para identificar y eliminar asignaciones de variables que nunca se utilizan (`usos == 0`).
- **Detección de similitud estructural:** extrae n-gramas (*k-shingles*) de las huellas estructurales depuradas y calcula el coeficiente de similitud de Jaccard entre funciones.
- **Manipulación automática del código:** utiliza `TokenStreamRewriter` para generar dos versiones modificadas del código fuente, preservando la sintaxis válida de Python.

## 2. Estructura del proyecto

La organización de los directorios y archivos es la siguiente:

```text
CodeGuard-Py/
│
├── gramatica/
│   ├── Python3Lexer.g4
│   ├── Python3Parser.g4
│   ├── Python3LexerBase.py
│   ├── Python3ParserBase.py
│   └── transformGrammar.py
│
├── src/
│   ├── generated/
│   │   ├── Python3Lexer.py
│   │   ├── Python3Parser.py
│   │   └── Python3ParserListener.py
│   │
│   ├── codeguard_py.py
│   └── app.py
│
│
└── README.md
```

**Descripción de los directorios principales:**

- `gramatica/`: contiene la gramática de Python 3, los archivos base y los scripts necesarios para su adaptación.
- `src/`: contiene el código fuente de la aplicación.
- `src/generated/`: almacena los archivos generados por ANTLR v4 (Lexer, Parser y Listener), necesarios para analizar el código.
- `ejemplos/`: contiene los archivos de prueba utilizados para demostrar el funcionamiento del detector.
- `ejemplos/salidas/`: almacena los archivos generados durante el análisis mediante la CLI.

## 3. Requisitos previos

Antes de instalar el proyecto, es necesario contar con los siguientes componentes:

- **Python 3.10 o superior.**
- **Conexión a Internet:** necesaria inicialmente para descargar las dependencias mediante `pip`.
- **Java (JRE/JDK 11 o superior):** únicamente necesario si se desea recompilar los archivos de gramática `.g4` utilizando ANTLR. Para ejecutar la aplicación con los archivos previamente compilados incluidos en `src/generated/`, no se requiere Java.

## 4. Instalación de dependencias

Ubíquese en el directorio raíz del proyecto (`CodeGuard-Py/`) y seleccione una de las siguientes alternativas según su sistema operativo.

### Opción A. Instalación mediante entorno virtual (recomendada)

Se recomienda utilizar un entorno virtual para evitar conflictos con las dependencias del sistema y prevenir restricciones de instalación como las establecidas por PEP 668 en distribuciones Linux modernas.

**1. Crear el entorno virtual:**

```bash
python3 -m venv .venv
```

**2. Activar el entorno virtual:**

Linux / macOS:

```bash
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

**3. Instalar las dependencias:**

```bash
pip install antlr4-python3-runtime antlr4-tools streamlit
```

### Opción B. Instalación directa

En sistemas Windows o entornos donde se permita la instalación global mediante `pip`, se pueden instalar las dependencias directamente:

```bash
pip install antlr4-python3-runtime antlr4-tools streamlit
```

## 5. Compilación de la gramática ANTLR v4 (opcional)

El directorio `src/generated/` incluye los archivos del Lexer, Parser y Listener previamente compilados, por lo que este procedimiento no es necesario para ejecutar directamente la aplicación.

Si se desea regenerar los archivos a partir de la gramática original, se deben seguir estos pasos:

**1. Ingresar al directorio de la gramática y ejecutar el script de adaptación:**

```bash
cd gramatica
python3 transformGrammar.py
```

**2. Compilar los archivos `.g4`:**

Se debe especificar explícitamente la versión de ANTLR para garantizar su compatibilidad con `antlr4-python3-runtime`.

Ejemplo utilizando la versión `4.13.2`:

Linux / macOS:

```bash
ANTLR4_TOOLS_ANTLR_VERSION=4.13.2 antlr4 -Dlanguage=Python3 -o ../src/generated Python3Lexer.g4 Python3Parser.g4
```

Windows (PowerShell):

```powershell
$env:ANTLR4_TOOLS_ANTLR_VERSION="4.13.2"; antlr4 -Dlanguage=Python3 -o ../src/generated Python3Lexer.g4 Python3Parser.g4
```

**3. Copiar las clases base al directorio generado y regresar a la raíz del proyecto:**

Linux / macOS:

```bash
cp Python3LexerBase.py Python3ParserBase.py ../src/generated/
cd ..
```

## 6. Ejecución de la aplicación

Asegúrese de estar ubicado en el directorio raíz del proyecto y de tener activado el entorno virtual, si utilizó la opción A.

CodeGuard-Py ofrece dos modalidades de ejecución:

### Modo 1. Interfaz gráfica web con Streamlit (recomendado)

Para iniciar la aplicación, ejecute:

```bash
streamlit run src/app.py
```

Una vez iniciado el servidor, se abrirá una pestaña en el navegador con la siguiente dirección:

[http://localhost:8501](http://localhost:8501)

Desde la interfaz gráfica es posible:

- Cargar archivos `.py` propios para realizar la comparación entre un archivo base y uno sospechoso.
- Ejecutar escenarios de demostración integrados desde la barra lateral:
  - `Demo: Plagio Camuflado`.
  - `Demo: Código Independiente`.
- Configurar el umbral de similitud en porcentaje.
- Modificar el tamaño de los n-gramas utilizados en el análisis.
- Inspeccionar la tabla de símbolos y los resultados del rastreo Def-Use.
- Visualizar y descargar los archivos generados por el sistema.

### Modo 2. Ejecución por línea de comandos (CLI)

El sistema también permite realizar análisis directamente desde la terminal.

**1. Generar los tres archivos de prueba en el directorio `ejemplos/`:**

```bash
python3 src/codeguard_py.py --crear-ejemplos
```

**2. Analizar un caso de plagio camuflado:**

```bash
python3 src/codeguard_py.py ejemplos/entrada_original.py ejemplos/entrada_plagio_camuflado.py
```

**3. Analizar una implementación independiente:**

```bash
python3 src/codeguard_py.py ejemplos/entrada_original.py ejemplos/entrada_independiente.py
```

**Parámetros opcionales:**

| Parámetro | Descripción | Valor predeterminado |
|---|---|---|
| `--umbral` | Porcentaje mínimo de similitud para generar una alerta. | `70.0` |
| `--ngramas` | Tamaño `k` de las ventanas de tokens utilizadas para calcular la similitud. | `5` |

Ejemplo de ejecución modificando ambos parámetros:

```bash
python3 src/codeguard_py.py ejemplos/entrada_original.py ejemplos/entrada_plagio_camuflado.py --umbral 75.0 --ngramas 5
```

## 7. Archivos de salida generados

Por cada evaluación, CodeGuard-Py genera dos archivos mediante `TokenStreamRewriter`. Estos pueden descargarse desde la interfaz web o consultarse en el directorio `ejemplos/salidas/` cuando se utiliza la CLI.

### 1. Archivo canonizado

**Nombre:** `canonizado_<archivo>.py`

Genera una versión estandarizada y depurada del código evaluado. Sus principales características son:

- Renombra las funciones mediante identificadores normalizados (`FUNC_i`).
- Estandariza los parámetros (`PARAM_i`).
- Estandariza las variables locales activas (`LOCAL_i`).
- Omite los comentarios del código fuente.
- Elimina automáticamente las asignaciones correspondientes a variables locales sin uso detectado.

### 2. Archivo anotado

**Nombre:** `anotado_<archivo>.py`

Conserva el código fuente original y agrega comentarios de alerta encima de las funciones que superan el umbral de similitud establecido.

Ejemplo de alerta generada:

```python
# [ALERTA DE PLAGIO: 85.5% de similitud con 'busqueda_binaria']
def encontrar_elemento(arreglo, valor_buscado):
    ...
```

## 8. Solución de problemas frecuentes (Troubleshooting)

A continuación, se describen algunos inconvenientes que pueden presentarse durante la instalación y ejecución del proyecto.

### Problema 1. Error `externally-managed-environment` (PEP 668)

**Causa:** algunas distribuciones Linux modernas, como Arch Linux, Ubuntu 23.04+ y Debian 12+, restringen las instalaciones globales mediante `pip` para proteger los paquetes administrados por el sistema.

**Solución:** crear y activar un entorno virtual siguiendo los pasos de la sección 4:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Posteriormente, instalar las dependencias dentro del entorno virtual.

### Problema 2. Error `HTTP Error 400: Bad Request` o `FileNotFoundError: .../.m2/repository`

**Causa:** `antlr4-tools` puede presentar inconvenientes al consultar automáticamente la versión disponible de ANTLR en Maven Central.

**Solución:** definir manualmente la variable de entorno `ANTLR4_TOOLS_ANTLR_VERSION`, utilizando la misma versión instalada de `antlr4-python3-runtime`.

Para consultar la versión instalada:

```bash
pip show antlr4-python3-runtime
```

Ejemplo de compilación:

```bash
ANTLR4_TOOLS_ANTLR_VERSION=4.13.2 antlr4 -Dlanguage=Python3 -o ../src/generated Python3Lexer.g4 Python3Parser.g4
```

### Problema 3. Error: no se encontraron los archivos compilados de la gramática

**Causa:** faltan los archivos generados por ANTLR o las clases base necesarias para el funcionamiento del Lexer y Parser.

**Solución:** verificar que el directorio `src/generated/` contenga los siguientes archivos:

- `Python3Lexer.py`
- `Python3Parser.py`
- `Python3ParserListener.py`
- `Python3LexerBase.py`
- `Python3ParserBase.py`

Si faltan, seguir el procedimiento de compilación descrito en la sección 5.

### Problema 4. Error relacionado con Java durante la compilación de los archivos `.g4`

**Causa:** `antlr4-tools` utiliza el archivo `.jar` oficial de ANTLR para compilar la gramática, por lo que necesita una instalación de Java.

**Solución:** instalar OpenJDK según la distribución utilizada.

Arch Linux / Manjaro:

```bash
sudo pacman -S jdk-openjdk
```

Ubuntu / Debian:

```bash
sudo apt install default-jre
```

Como alternativa, si no se necesita modificar la gramática, se pueden utilizar directamente los archivos previamente compilados incluidos en `src/generated/`.

---

## 9. Tecnologías utilizadas

| Tecnología | Función dentro del proyecto |
|---|---|
| Python 3 | Lenguaje de programación principal. |
| ANTLR v4 | Generación del Lexer, Parser y Listener para analizar código Python. |
| grammars-v4 | Fuente de la gramática de Python 3 utilizada por ANTLR. |
| TokenStreamRewriter | Manipulación y generación de las versiones modificadas del código fuente. |
| Streamlit | Desarrollo de la interfaz gráfica web. |
| Coeficiente de Jaccard | Medición de similitud entre las huellas estructurales de las funciones. |

---

**CodeGuard-Py**  
Proyecto académico desarrollado para la asignatura Lenguajes de Programación de la Universidad Nacional de Colombia.
