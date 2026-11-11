import os
import random
import socket
import struct
import time

IP = "127.0.0.1"
PUERTO = 9999
TAM_PAQUETE = 1024      # Bytes de música en cada paquete
TAM_VENTANA = 5         # Máximo de paquetes sin confirmar
TIEMPO_ESPERA = 0.5     # Segundos para recibir un ACK
PERDIDA = 0.20          # 5 % de pérdidas simuladas
CARPETA = "musica"
FORMATO_CABECERA = "!I?H"  # Número, último paquete, tamaño
FORMATO_ACK = "!I"         # Número del paquete confirmado


def enviar_cancion(conexion, direccion, ruta):
    with open(ruta, "rb") as archivo:
        musica = archivo.read()

    partes = [musica[i:i + TAM_PAQUETE] for i in range(0, len(musica), TAM_PAQUETE)]
    if not partes:
        partes = [b""]

    base = 0       # Primer paquete que todavía no tiene confirmación
    siguiente = 0  # Próximo paquete que vamos a enviar
    inicio = None  # Inicio del temporizador de la ventana
    intentos = 0
    print(f"Se enviarán {len(partes)} paquetes. Ventana: {TAM_VENTANA}")

    while base < len(partes):
        # Enviar hasta llenar la ventana.
        while siguiente < min(base + TAM_VENTANA, len(partes)):
            datos = partes[siguiente]
            ultimo = (siguiente == len(partes) - 1)
            cabecera = struct.pack(FORMATO_CABECERA, siguiente, ultimo, len(datos))
            if random.random() < PERDIDA:
                print(f"[PÉRDIDA] Paquete {siguiente} no enviado")
            else:
                conexion.sendto(cabecera + datos, direccion)
                print(f"[ENVÍO] Paquete {siguiente}")
            if base == siguiente:
                inicio = time.monotonic()
            siguiente += 1

        # Si no llega el ACK a tiempo, reenviar desde base (Go-Back-N).
        restante = TIEMPO_ESPERA - (time.monotonic() - inicio)
        if restante <= 0:
            print(f"[TIMEOUT] Volviendo al paquete {base}")
            siguiente = base
            inicio = None
            intentos += 1
            if intentos >= 60:
                print("[ERROR] No se pudo terminar la transferencia")
                return
            continue

        conexion.settimeout(restante)
        try:
            respuesta, origen = conexion.recvfrom(1024)
        except socket.timeout:
            continue

        if origen != direccion or len(respuesta) != struct.calcsize(FORMATO_ACK):
            continue
        (confirmado,) = struct.unpack(FORMATO_ACK, respuesta)
        if base <= confirmado < siguiente:
            print(f"[ACK] Confirmado hasta {confirmado}")
            base = confirmado + 1
            intentos = 0
            inicio = time.monotonic() if base < siguiente else None

    print("[LISTO] Canción enviada y confirmada")


def main():
    os.makedirs(CARPETA, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conexion:
        conexion.bind((IP, PUERTO))
        print(f"Servidor UDP en {IP}:{PUERTO}")
        while True:
            conexion.settimeout(None)
            print("\nEsperando cliente...")
            mensaje, direccion = conexion.recvfrom(4096)
            if mensaje != b"GET_CATALOG":
                continue

            canciones = sorted(nombre for nombre in os.listdir(CARPETA)
                               if nombre.lower().endswith(".mp3")
                               and os.path.isfile(os.path.join(CARPETA, nombre)))
            if not canciones:
                conexion.sendto(b"ERROR:No hay archivos MP3 en musica", direccion)
                continue

            catalogo = ("CATALOG:" + ",".join(canciones)).encode("utf-8")
            if len(catalogo) > 4096:
                conexion.sendto(b"ERROR:Demasiadas canciones", direccion)
                continue
            conexion.sendto(catalogo, direccion)

            conexion.settimeout(15)
            try:
                while True:
                    pedido, origen = conexion.recvfrom(4096)
                    if origen == direccion:
                        break
            except socket.timeout:
                print("El cliente no eligió una canción")
                continue

            nombre = pedido.decode("utf-8", errors="replace")
            if nombre not in canciones:
                conexion.sendto(b"ERROR:Cancion no disponible", direccion)
                continue
            print("Canción solicitada:", nombre)
            enviar_cancion(conexion, direccion, os.path.join(CARPETA, nombre))


if __name__ == "__main__":
    main()
