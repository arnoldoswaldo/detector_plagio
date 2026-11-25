================================================================================
CodeGuard-Py: Detector de Plagio con Semántica Ligera y Manipulación Automática
================================================================================
Asignatura : Lenguajes de Programación
Tecnologías: Python 3, ANTLR v4 (grammars-v4 Python3) y Streamlit

--------------------------------------------------------------------------------
1. DESCRIPCIÓN DEL PROYECTO
--------------------------------------------------------------------------------
CodeGuard-Py es una herramienta de análisis estático y manipulación automática de
código fuente en Python 3 desarrollada con ANTLR v4. A partir del recorrido del
árbol sintáctico (ParseTreeListener), el sistema combina análisis estructural
con un nivel de semántica ligera:

  - Tabla de símbolos local por función: clasifica identificadores según su rol
    semántico (parámetros como PARAM_i y variables locales como LOCAL_i) y
    conserva llamadas a funciones nativas de Python (len, range, print, etc.).
  - Rastreo básico Def-Use (Código Muerto): contabiliza definiciones y usos de
    cada variable local para detectar y eliminar asignaciones de variables que
    nunca se utilizan (usos == 0).
  - Detección de similitud: extrae n-gramas (k-shingles) de la huella estructural
    depurada y calcula el coeficiente de similitud de Jaccard entre funciones.
  - Manipulación automática (TokenStreamRewriter): genera dos archivos .py
    modificados sin alterar la sintaxis válida de Python.

--------------------------------------------------------------------------------
2. ESTRUCTURA DE CARPETAS
--------------------------------------------------------------------------------
CodeGuard-Py/
├── gramatica/                  # Gramática oficial Python 3 (.g4) y scripts base
│   ├── Python3Lexer.g4
│   ├── Python3Parser.g4
│   ├── Python3LexerBase.py
│   ├── Python3ParserBase.py
│   └── transformGrammar.py
├── src/                        # Código fuente de la aplicación
│   ├── generated/              # Lexer, Parser y Listener generados por ANTLR
│   ├── codeguard_py.py         # Motor de análisis, tabla de símbolos y CLI
│   └── app.py                  # Interfaz gráfica web en Streamlit
├── ejemplos/                   # Casos de prueba y carpeta de salidas
│   ├── entrada_original.py
│   ├── entrada_plagio_camuflado.py
│   ├── entrada_independiente.py
│   └── salidas/
└── README.txt                  # Este manual de instalación y ejecución

--------------------------------------------------------------------------------
3. REQUISITOS PREVIOS
--------------------------------------------------------------------------------
  - Python 3.10 o superior.
  - Conexión a internet la primera vez que se instalen dependencias con pip.
  - Java (JRE/JDK 11+): únicamente necesario si se desea recompilar los
    archivos .g4 desde cero usando antlr4-tools. (Para ejecutar la aplicación
    directamente usando los archivos ya compilados en src/generated/ NO se
    requiere Java).

--------------------------------------------------------------------------------
4. INSTALACIÓN DE DEPENDENCIAS
--------------------------------------------------------------------------------
Ubíquese en la carpeta raíz del proyecto (CodeGuard-Py/) y elija una de las
siguientes opciones según su sistema operativo:

OPCIÓN A: Usando entorno virtual venv (RECOMENDADA - Linux / Arch / Ubuntu / Mac)
Evita conflictos con paquetes del sistema y soluciona el bloqueo PEP 668
("externally-managed-environment"):

  1. Crear el entorno virtual:
     python3 -m venv .venv

  2. Activar el entorno virtual:
     - En Linux / macOS:
       source .venv/bin/activate
     - En Windows (PowerShell):
       .venv\Scripts\Activate.ps1

  3. Instalar las dependencias dentro del entorno activo:
     pip install antlr4-python3-runtime antlr4-tools streamlit

OPCIÓN B: Instalación directa (Windows o entornos sin restricción PEP 668)
Si su sistema permite instalaciones globales con pip:

  pip install antlr4-python3-runtime antlr4-tools streamlit

--------------------------------------------------------------------------------
5. COMPILACIÓN DE LA GRAMÁTICA ANTLR v4 (OPCIONAL)
--------------------------------------------------------------------------------
Nota: El directorio src/generated/ ya incluye el Lexer y Parser compilados y
listos para usar. Si desea regenerarlos manualmente desde gramatica/:

  1. Ingrese a la carpeta de la gramática y adapte los predicados a Python 3:
     cd gramatica
     python3 transformGrammar.py

  2. Compile los archivos .g4 especificando explícitamente la versión de ANTLR
     (debe coincidir con la versión de antlr4-python3-runtime instalada, ej. 4.13.2):
     ANTLR4_TOOLS_ANTLR_VERSION=4.13.2 antlr4 -Dlanguage=Python3 -o ../src/generated Python3Lexer.g4 Python3Parser.g4

     (En Windows PowerShell):
     $env:ANTLR4_TOOLS_ANTLR_VERSION="4.13.2"; antlr4 -Dlanguage=Python3 -o ../src/generated Python3Lexer.g4 Python3Parser.g4

  3. Copie las clases base al directorio generado y regrese a la raíz:
     cp Python3LexerBase.py Python3ParserBase.py ../src/generated/
     cd ..

--------------------------------------------------------------------------------
6. EJECUCIÓN DE LA APLICACIÓN
--------------------------------------------------------------------------------
Asegúrese de estar en la carpeta raíz (CodeGuard-Py/) y tener el entorno
virtual activado (si usó la Opción A).

MODO 1: Interfaz Gráfica Web con Streamlit (Recomendado)
  Ejecute:
    streamlit run src/app.py

  Se abrirá automáticamente una pestaña en su navegador (http://localhost:8501).
  Desde allí podrá:
    - Subir sus propios archivos .py (Archivo Base y Archivo Sospechoso).
    - Probar los escenarios integrados desde la barra lateral ("Demo: Plagio
      Camuflado" y "Demo: Código Independiente").
    - Ajustar el umbral de similitud (%) y el tamaño de n-gramas.
    - Inspeccionar la tabla de símbolos (Def-Use) y descargar los archivos
      manipulados.

MODO 2: Ejecución por Línea de Comandos (CLI)
  1. Generar los 3 archivos de prueba en la carpeta ejemplos/:
     python3 src/codeguard_py.py --crear-ejemplos

  2. Analizar el caso de plagio camuflado:
     python3 src/codeguard_py.py ejemplos/entrada_original.py ejemplos/entrada_plagio_camuflado.py

  3. Analizar el caso de implementación independiente:
     python3 src/codeguard_py.py ejemplos/entrada_original.py ejemplos/entrada_independiente.py

  Parámetros opcionales en CLI:
    --umbral 75.0    Cambia el porcentaje mínimo de similitud para alertar.
    --ngramas 5      Cambia el tamaño k de las ventanas de tokens.

--------------------------------------------------------------------------------
7. ARCHIVOS DE SALIDA GENERADOS
--------------------------------------------------------------------------------
Por cada evaluación realizada, CodeGuard-Py genera dos archivos manipulados
mediante TokenStreamRewriter (disponibles para descarga en la interfaz web o
guardados en ejemplos/salidas/ al usar la CLI):

  1. canonizado_<nombre>.py:
     Versión estandarizada y depurada del archivo evaluado. Renombra funciones
     (FUNC_i), parámetros (PARAM_i) y variables locales (LOCAL_i), omite todos
     los comentarios (#) y elimina automáticamente las líneas de asignación de
     variables muertas (declaradas y nunca usadas).

  2. anotado_<nombre>.py:
     Conserva el código fuente original intacto e inserta comentarios de alerta
     ('# [ALERTA DE PLAGIO: XX.X% de similitud...]') justo encima de cada
     función que supere el umbral establecido.

--------------------------------------------------------------------------------
8. SOLUCIÓN DE PROBLEMAS FRECUENTES (TROUBLESHOOTING)
--------------------------------------------------------------------------------
Problema 1: Error "externally-managed-environment" (PEP 668) al ejecutar pip.
  - Causa: Distribuciones Linux modernas (como Arch Linux, Ubuntu 23.04+ o
    Debian 12+) bloquean pip global para proteger los paquetes del sistema.
  - Solución: Utilice un entorno virtual siguiendo los pasos de la Opción A en
    la Sección 4 ("python3 -m venv .venv" y "source .venv/bin/activate").

Problema 2: Error "HTTP Error 400: Bad Request" o "FileNotFoundError: .../.m2/repository"
            al ejecutar el comando antlr4.
  - Causa: antlr4-tools intenta consultar una URL antigua de Maven Central para
    detectar automáticamente la última versión de ANTLR disponible.
  - Solución: Defina la variable de entorno ANTLR4_TOOLS_ANTLR_VERSION con la
    misma versión de antlr4-python3-runtime instalada (puede verificarla con
    "pip show antlr4-python3-runtime"). Ejemplo:
    ANTLR4_TOOLS_ANTLR_VERSION=4.13.2 antlr4 -Dlanguage=Python3 -o ../src/generated Python3Lexer.g4 Python3Parser.g4

Problema 3: Error "No se encontraron los archivos compilados de la gramática".
  - Causa: Faltan los archivos generados o las clases base en src/generated/.
  - Solución: Verifique que dentro de src/generated/ existan Python3Lexer.py,
    Python3Parser.py, Python3ParserListener.py, Python3LexerBase.py y
    Python3ParserBase.py (ver Sección 5).

Problema 4: Error de Java al intentar compilar los archivos .g4.
  - Causa: antlr4-tools descarga y ejecuta el archivo .jar oficial de ANTLR, el
    cual requiere tener Java instalado.
  - Solución: Instale OpenJDK (ej. "sudo pacman -S jdk-openjdk" o
    "sudo apt install default-jre") o utilice directamente los archivos ya
    compilados incluidos en src/generated/.
================================================================================
