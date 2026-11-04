import os
import random
import socket
import struct
import time

SERVER_IP = "127.0.0.1"
SERVER_PORT = 9999

# Parámetros del protocolo
BUFFER_SIZE = 1024          
HEADER_FORMAT = "!I?H"      
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
ACK_FORMAT = "!I"           
WINDOW_SIZE = 5             
TIMEOUT = 0.5               

PROBABILIDAD_PERDIDA = 0.05 

CARPETA_MUSICA = "musica"

def obtener_catalogo():
    if not os.path.exists(CARPETA_MUSICA):
        os.makedirs(CARPETA_MUSICA)
    return [f for f in os.listdir(CARPETA_MUSICA) if f.lower().endswith(".mp3")]

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVER_IP, SERVER_PORT))
    print(f"=== SERVIDOR UDP INICIADO EN {SERVER_IP}:{SERVER_PORT} ===")

    while True:
        sock.settimeout(None)
        print("\nEsperando solicitud de un cliente...")
        data, cliente_addr = sock.recvfrom(1024)
        mensaje = data.decode("utf-8", errors="ignore")

        if mensaje == "GET_CATALOG":
            catalogo = obtener_catalogo()
            if not catalogo:
                sock.sendto(b"ERROR:No hay canciones .mp3 en la carpeta 'musica'", cliente_addr)
                continue
            
            sock.sendto(("CATALOG:" + ",".join(catalogo)).encode("utf-8"), cliente_addr)

            data, cliente_addr = sock.recvfrom(1024)
            cancion_elegida = data.decode("utf-8", errors="ignore")
            ruta_cancion = os.path.join(CARPETA_MUSICA, cancion_elegida)

            if not os.path.exists(ruta_cancion):
                sock.sendto(b"ERROR:Archivo no encontrado", cliente_addr)
                continue

            print(f"\n[INICIO] Cliente {cliente_addr} solicitó: {cancion_elegida}")

            with open(ruta_cancion, "rb") as f:
                datos_completos = f.read()

            chunks = [datos_completos[i:i + BUFFER_SIZE] for i in range(0, len(datos_completos), BUFFER_SIZE)]
            total_paquetes = len(chunks)
            print(f"[PREPARACIÓN] Total de fragmentos a enviar: {total_paquetes}")

            sock.settimeout(TIMEOUT)
            base = 0
            next_seq_num = 0

            while base < total_paquetes:
                while next_seq_num < base + WINDOW_SIZE and next_seq_num < total_paquetes:
                    is_last = (next_seq_num == total_paquetes - 1)
                    payload = chunks[next_seq_num]
                    header = struct.pack(HEADER_FORMAT, next_seq_num, is_last, len(payload))
                    paquete = header + payload

                    if random.random() >= PROBABILIDAD_PERDIDA:
                        sock.sendto(paquete, cliente_addr)
                        print(f"[ENVÍO] Paquete {next_seq_num}")
                    else:
                        print(f"*** [SIMULACIÓN] Paquete {next_seq_num} se perdió en el canal ***")

                    next_seq_num += 1

                try:
                    ack_data, _ = sock.recvfrom(struct.calcsize(ACK_FORMAT))
                    ack_num, = struct.unpack(ACK_FORMAT, ack_data)
                    print(f"      [ACK] Recibido ACK: {ack_num}")

                    if ack_num >= base:
                        base = ack_num + 1

                except socket.timeout:
                    print(f"\n--> [TIMEOUT] Expiró el tiempo de espera. RETROCEDIENDO ventana a base: {base}\n")
                    next_seq_num = base

            print(f"[ÉXITO] Transferencia completa de '{cancion_elegida}'.")

if __name__ == "__main__":
    main()