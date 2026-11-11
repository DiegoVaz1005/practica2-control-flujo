import os
import platform
import socket
import struct
import subprocess
import time

IP_SERVIDOR = "127.0.0.1"
PUERTO = 9999
TAM_PAQUETE = 1024
FORMATO_CABECERA = "!I?H"
TAM_CABECERA = struct.calcsize(FORMATO_CABECERA)
FORMATO_ACK = "!I"
TIEMPO_ESPERA = 10


def metadatos(datos):
    info = {"Título": "Desconocido", "Artista": "Desconocido",
            "Álbum": "Desconocido", "Año": "Desconocido"}
    campos = {"TIT2": "Título", "TPE1": "Artista",
              "TALB": "Álbum", "TYER": "Año", "TDRC": "Año"}

    if datos[:3] == b"ID3" and len(datos) >= 10 and datos[3] in (3, 4):
        version = datos[3]
        tam = 0
        for valor in datos[6:10]:
            tam = (tam << 7) | (valor & 127)
        posicion = 10
        limite = min(len(datos), 10 + tam)
        if datos[5] & 0x40 and posicion + 4 <= limite:
            extra = datos[posicion:posicion + 4]
            if version == 3:
                posicion += 4 + struct.unpack("!I", extra)[0]
            else:
                posicion += sum((extra[i] & 127) << (7 * (3-i)) for i in range(4))
        while posicion + 10 <= limite:
            clave = datos[posicion:posicion + 4].decode("latin-1")
            if not clave.isalnum():
                break
            tam_bytes = datos[posicion + 4:posicion + 8]
            if version == 3:
                longitud = struct.unpack("!I", tam_bytes)[0]
            else:
                longitud = sum((tam_bytes[i] & 127) << (7 * (3-i)) for i in range(4))
            banderas = datos[posicion + 9]
            posicion += 10
            if longitud <= 0 or posicion + longitud > limite:
                break
            contenido = datos[posicion:posicion + longitud]
            if clave in campos and contenido and not (banderas & 0x0C):
                codificacion = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(contenido[0])
                if codificacion:
                    texto = contenido[1:].decode(codificacion, errors="replace").split("\x00")[0].strip()
                    if texto:
                        info[campos[clave]] = texto
            posicion += longitud
    elif len(datos) >= 128 and datos[-128:-125] == b"TAG":
        etiqueta = datos[-128:]
        for nombre, inicio, fin in (("Título", 3, 33), ("Artista", 33, 63),
                                    ("Álbum", 63, 93), ("Año", 93, 97)):
            info[nombre] = etiqueta[inicio:fin].decode("latin-1", errors="replace").strip("\x00 ") or "Desconocido"

    print("\nMetadatos del MP3:")
    for nombre, valor in info.items():
        print(f"{nombre}: {valor}")


def reproducir(ruta):
    print("Abriendo:", ruta)
    try:
        if platform.system() == "Windows":
            os.startfile(ruta)
        elif platform.system() == "Darwin":
            subprocess.run(["afplay", ruta], check=False)
        else:
            for programa in ("ffplay", "mpg123", "mpv"):
                if subprocess.call(["which", programa], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL) == 0:
                    opciones = ["-nodisp", "-autoexit"] if programa == "ffplay" else []
                    subprocess.run([programa, *opciones, ruta], check=False)
                    return
            print("No encontré reproductor: instala ffplay, mpg123 o mpv")
    except OSError as error:
        print("No se pudo reproducir:", error)


def recibir_cancion(conexion, servidor):
    esperado = 0  #numero del paquete que toca recibir
    musica = bytearray()
    conexion.settimeout(TIEMPO_ESPERA)

    while True:
        paquete, origen = conexion.recvfrom(TAM_CABECERA + TAM_PAQUETE + 1)
        if origen != servidor:
            continue
        if paquete.startswith(b"ERROR:"):
            raise RuntimeError(paquete.decode("utf-8", errors="replace"))
        if len(paquete) < TAM_CABECERA:
            continue
        numero, ultimo, tam = struct.unpack(FORMATO_CABECERA, paquete[:TAM_CABECERA])
        datos = paquete[TAM_CABECERA:]
        if tam != len(datos) or tam > TAM_PAQUETE:
            print("[DESCARTADO] Tamaño incorrecto")
            continue

        if numero == esperado:
            musica.extend(datos)
            conexion.sendto(struct.pack(FORMATO_ACK, numero), servidor)
            print(f"[RECIBIDO] Paquete {numero}; ACK enviado")
            esperado += 1
            if ultimo:
                break
        else:
            print(f"[FUERA DE ORDEN] Recibido {numero}, esperaba {esperado}")
            if esperado > 0:
                conexion.sendto(struct.pack(FORMATO_ACK, esperado - 1), servidor)

    fin_espera = time.monotonic() + 2
    while time.monotonic() < fin_espera:
        conexion.settimeout(max(0.001, fin_espera - time.monotonic()))
        try:
            paquete, origen = conexion.recvfrom(TAM_CABECERA + TAM_PAQUETE + 1)
        except socket.timeout:
            break
        if origen != servidor or len(paquete) < TAM_CABECERA:
            continue
        numero, _, tam = struct.unpack(FORMATO_CABECERA, paquete[:TAM_CABECERA])
        if numero < esperado and tam <= TAM_PAQUETE and tam == len(paquete) - TAM_CABECERA:
            conexion.sendto(struct.pack(FORMATO_ACK, esperado - 1), servidor)
            print("[ACK REPETIDO] Confirmación reenviada")
    return musica


def main():
    servidor = (IP_SERVIDOR, PUERTO)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conexion:
        conexion.settimeout(5)
        try:
            conexion.sendto(b"GET_CATALOG", servidor)
            respuesta, origen = conexion.recvfrom(4096)
            if origen != servidor:
                print("Respuesta de otro equipo")
                return
            mensaje = respuesta.decode("utf-8", errors="replace")
            if mensaje.startswith("ERROR:"):
                print(mensaje)
                return
            if not mensaje.startswith("CATALOG:"):
                print("Catálogo incorrecto")
                return
            canciones = mensaje[len("CATALOG:"):].split(",")
            print("\nCanciones disponibles:")
            for numero, nombre in enumerate(canciones, 1):
                print(f"{numero}. {nombre}")
            opcion = int(input("Elige una canción: "))
            if not 1 <= opcion <= len(canciones):
                print("Opción inválida")
                return
            nombre = canciones[opcion - 1]
            conexion.sendto(nombre.encode("utf-8"), servidor)
            musica = recibir_cancion(conexion, servidor)
        except (ValueError, socket.timeout, RuntimeError, OSError) as error:
            print("Error durante la transferencia:", error)
            return

    ruta = "descarga_" + os.path.basename(nombre)
    with open(ruta, "wb") as archivo:
        archivo.write(musica)
    print(f"\nArchivo guardado: {ruta} ({len(musica)} bytes)")
    metadatos(musica)
    reproducir(ruta)


if __name__ == "__main__":
    main()
