import os
import platform
import socket
import struct
import subprocess

SERVER_IP = "127.0.0.1"
SERVER_PORT = 9999

HEADER_FORMAT = "!I?H"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
ACK_FORMAT = "!I"

def parsear_id3v2(datos):
    if len(datos) < 10 or datos[:3] != b"ID3":
        return None

    tam_header = ((datos[6] & 0x7F) << 21) | ((datos[7] & 0x7F) << 14) | ((datos[8] & 0x7F) << 7) | (datos[9] & 0x7F)
    pos = 10
    limite = min(len(datos), 10 + tam_header)

    metadatos = {"TIT2": "Desconocido", "TPE1": "Desconocido", "TALB": "Desconocido", "TYER": "Desconocido", "TDRC": "Desconocido"}

    while pos + 10 < limite:
        frame_id = datos[pos:pos+4].decode("latin-1", errors="ignore")
        if not frame_id.isalnum():
            break

        tam_frame = struct.unpack("!I", datos[pos+4:pos+8])[0]
        pos += 10

        if pos + tam_frame > limite:
            break

        contenido = datos[pos:pos+tam_frame]
        if len(contenido) > 1 and contenido[0] in (0, 1, 2, 3):
            contenido = contenido[1:]

        texto = contenido.decode("latin-1", errors="ignore").replace("\x00", "").strip()

        if frame_id in metadatos:
            metadatos[frame_id] = texto

        pos += tam_frame

    anio = metadatos["TYER"] if metadatos["TYER"] != "Desconocido" else metadatos["TDRC"]
    return {
        "Titulo": metadatos["TIT2"],
        "Artista": metadatos["TPE1"],
        "Album": metadatos["TALB"],
        "Anio": anio
    }

def parsear_id3v1(datos):
    if len(datos) < 128:
        return None
    
    tag = datos[-128:]
    if tag[:3] != b"TAG":
        return None

    return {
        "Titulo": tag[3:33].decode("latin-1", errors="ignore").strip("\x00 "),
        "Artista": tag[33:63].decode("latin-1", errors="ignore").strip("\x00 "),
        "Album": tag[63:93].decode("latin-1", errors="ignore").strip("\x00 "),
        "Anio": tag[93:97].decode("latin-1", errors="ignore").strip("\x00 ")
    }

def mostrar_metadatos(datos_completos):
    print("\n" + "=" * 45)
    print("           METADATOS DEL ARCHIVO")
    print("=" * 45)
    
    info = parsear_id3v2(datos_completos)
    version = "ID3v2"
    if not info:
        info = parsear_id3v1(datos_completos)
        version = "ID3v1"

    if info:
        print(f"Formato detectado: {version}")
        print(f"Título:  {info['Titulo'] or 'Desconocido'}")
        print(f"Artista: {info['Artista'] or 'Desconocido'}")
        print(f"Álbum:   {info['Album'] or 'Desconocido'}")
        print(f"Año:     {info['Anio'] or 'Desconocido'}")
    else:
        print("No se encontraron etiquetas legibles (ID3v1 o ID3v2).")
    print("=" * 45 + "\n")

def reproducir(ruta):
    print(f"[REPRODUCTOR] Abriendo '{ruta}'...")
    sistema = platform.system()
    try:
        if sistema == "Windows":
            os.startfile(ruta)
        elif sistema == "Darwin":
            subprocess.run(["afplay", ruta])
        else:  # Linux
            for player in ["ffplay", "mpg123", "mpv"]:
                if subprocess.call(["which", player], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                    args = ["-nodisp", "-autoexit"] if player == "ffplay" else []
                    subprocess.run([player] + args + [ruta])
                    return
            print("En Linux instala un reproductor CLI: sudo apt install mpg123 ffplay")
    except Exception as e:
        print(f"Error al reproducir: {e}")

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print("Solicitando catálogo de canciones al servidor...")
    sock.sendto(b"GET_CATALOG", (SERVER_IP, SERVER_PORT))
    
    data, server_addr = sock.recvfrom(4096)
    respuesta = data.decode("utf-8", errors="ignore")

    if respuesta.startswith("ERROR:"):
        print(respuesta)
        return

    canciones = respuesta.replace("CATALOG:", "").split(",")
    print("\n--- CANCIONES DISPONIBLES EN EL SERVIDOR ---")
    for i, cancion in enumerate(canciones):
        print(f"  [{i + 1}] {cancion}")
    
    opcion = int(input("\nIngresa el número de la canción que deseas: ")) - 1
    cancion_elegida = canciones[opcion]

    sock.sendto(cancion_elegida.encode("utf-8"), server_addr)

    expected_seq_num = 0
    buffer_cancion = bytearray()
    print(f"\nIniciando descarga Go-Back-N de: {cancion_elegida}")

    while True:
        packet, addr = sock.recvfrom(HEADER_SIZE + 1024)
        if len(packet) < HEADER_SIZE:
            continue

        header = packet[:HEADER_SIZE]
        payload = packet[HEADER_SIZE:]
        seq_num, is_last, payload_size = struct.unpack(HEADER_FORMAT, header)

        if seq_num == expected_seq_num:
            print(f"[RECEPTOR] Paquete {seq_num} aceptado.")
            buffer_cancion.extend(payload[:payload_size])

            ack_packet = struct.pack(ACK_FORMAT, expected_seq_num)
            sock.sendto(ack_packet, addr)
            expected_seq_num += 1

            if is_last:
                print("\n[FIN TRANSMISIÓN] Archivo recibido en su totalidad.")
                break
        else:
            print(f"[DESCARTADO] Paquete {seq_num} fuera de orden (esperaba el {expected_seq_num}).")
            if expected_seq_num > 0:
                ack_packet = struct.pack(ACK_FORMAT, expected_seq_num - 1)
                sock.sendto(ack_packet, addr)

    sock.close()

    archivo_salida = f"descarga_{cancion_elegida}"
    with open(archivo_salida, "wb") as f:
        f.write(buffer_cancion)
    print(f"Archivo guardado localmente como '{archivo_salida}'.")

    mostrar_metadatos(buffer_cancion)
    reproducir(archivo_salida)

if __name__ == "__main__":
    main()