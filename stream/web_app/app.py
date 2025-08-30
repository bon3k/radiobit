from flask import Flask, render_template, redirect, url_for, request, send_file, jsonify
import os
import subprocess
import shutil
import urllib.parse
import re

app = Flask(__name__)

BASE_DIR = "/home/radiobit/stream/data"
FILE_PATH = os.path.join(BASE_DIR, "streams.txt")
VOLUME_FILE = "/usr/share/wireplumber/main.lua.d/40-device-defaults.lua"

def list_connections():
    connections = []
    result = subprocess.run(["sudo", "nmcli", "-t", "-f", "NAME,TYPE,STATE", "con"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        parts = line.split(":")
        if len(parts) == 3:
            name, type_, state = parts
            if name != "lo":
                connections.append({"name": name, "type": type_, "state": state})
    return connections


def update_m3u_on_add(folder, filename):
    """Añadir una pista al final del .m3u de la carpeta, si existe."""
    m3u_path = None
    for item in os.listdir(folder):
        if item.lower().endswith('.m3u'):
            m3u_path = os.path.join(folder, item)
            break

    if not m3u_path:
        return

    # Codificar el nombre como en el M3U original
    encoded_name = urllib.parse.quote(filename)

    # Leer líneas existentes y evitar duplicados
    try:
        with open(m3u_path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
    except Exception:
        lines = []

    if any(encoded_name in line for line in lines):
        return  # ya está en la lista

    # Si es un archivo de audio, añadirlo al final
    if filename.lower().endswith(('.mp3', '.flac', '.ogg', '.wav', '.aac', '.m4a', '.aiff', '.aif')):
        extinf_line = f"#EXTINF:-1,{os.path.splitext(filename)[0]}"
        with open(m3u_path, 'a', encoding='utf-8') as f:
            f.write(f"{extinf_line}\n{encoded_name}\n")


def update_m3u_on_delete(folder, filename):
    """Eliminar una pista del .m3u de la carpeta, si existe."""
    m3u_path = None
    for item in os.listdir(folder):
        if item.lower().endswith('.m3u'):
            m3u_path = os.path.join(folder, item)
            break

    if not m3u_path:
        return

    encoded_name = urllib.parse.quote(filename)

    try:
        with open(m3u_path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
    except Exception:
        lines = []

    new_lines = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        if line.strip().endswith(encoded_name):
            # Eliminar también la línea #EXTINF anterior si existe
            if i > 0 and lines[i-1].startswith("#EXTINF"):
                if new_lines:
                    new_lines.pop()
            continue
        new_lines.append(line)

    # Asegurarse de que #EXTM3U sea la primera línea
    if not new_lines or new_lines[0] != "#EXTM3U":
        new_lines.insert(0, "#EXTM3U")

    # Escribir línea por línea con '\n' explícito
    with open(m3u_path, 'w', encoding='utf-8') as f:
        for line in new_lines:
            f.write(line.rstrip('\r\n') + "\n")






@app.route('/')
def index():
    connections = list_connections()
    default_volume = get_default_volume()  # Leer valor actual
    return render_template('index.html', connections=connections, default_volume=default_volume)


@app.route('/edit_file', methods=['GET', 'POST'])
def edit_file():
    if request.method == 'POST':
        raw_links = request.form.to_dict(flat=True)
        new_links = [raw_links[key].strip() for key in sorted(raw_links) if "links[" in key and raw_links[key].strip()]
        with open(FILE_PATH, 'w') as f:
            f.write("\n".join(new_links))
        return redirect(url_for('index'))

    try:
        with open(FILE_PATH, 'r') as f:
            content = f.read().splitlines()
    except FileNotFoundError:
        content = []

    return render_template('edit_file.html', links=list(enumerate(content)))


@app.route('/delete/<name>', methods=['POST'])
def delete_connection(name):
    subprocess.run(["sudo", "nmcli", "con", "delete", name])
    return redirect(url_for('index'))


@app.route('/add', methods=['GET', 'POST'])
def add_connection():
    if request.method == 'POST':
        ssid = request.form['ssid']
        password = request.form['password']
        if ssid and password:
            subprocess.run(["sudo", "nmcli", "dev", "wifi", "connect", ssid, "password", password])
        return redirect(url_for('index'))
    return render_template('add.html')


@app.route('/file_manager/', defaults={'path': ''})
@app.route('/file_manager/<path:path>')
def file_manager(path):
    current_path = os.path.join(BASE_DIR, path)
    if not os.path.exists(current_path):
        return "Ruta no encontrada", 404

    # Buscar el primer archivo .m3u de la carpeta actual
    m3u_path = None
    for item in os.listdir(current_path):
        if item.lower().endswith('.m3u'):
            m3u_path = os.path.join(current_path, item)
            break

    # Leer el .m3u si existe
    playlist_order = []
    if m3u_path:
        with open(m3u_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    playlist_order.append(os.path.basename(line))

    # Crear un dict de todos los archivos y carpetas reales
    entries = {}
    for item in os.listdir(current_path):
        full_path = os.path.join(current_path, item)
        entries[item] = {
            "name": item,
            "path": os.path.relpath(full_path, BASE_DIR),
            "is_dir": os.path.isdir(full_path)
        }

    # Añadir primero los archivos que están en el .m3u
    ordered_items = []
    added = set()
    for name in playlist_order:
        if name in entries:
            ordered_items.append(entries[name])
            added.add(name)

    # Añadir el resto (archivos o carpetas) no listados en el .m3u
    for name in sorted(entries):
        if name not in added:
            ordered_items.append(entries[name])

    parent_path = "" if current_path == BASE_DIR else os.path.relpath(os.path.dirname(current_path), BASE_DIR)
    return render_template("file_manager.html", items=ordered_items, current_path=path, parent_path=parent_path)


@app.route('/upload/', defaults={'path': ''}, methods=['POST'])
@app.route('/upload/<path:path>', methods=['POST'])
def upload_file(path):
    current_path = os.path.join(BASE_DIR, path)

    if 'files' not in request.files:
        return redirect(url_for('file_manager', path=path))

    uploaded_files = request.files.getlist('files')
    for file in uploaded_files:
        if file.filename:
            safe_path = os.path.normpath(file.filename)
            dest_path = os.path.join(current_path, safe_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            file.save(dest_path)
            update_m3u_on_add(current_path, os.path.basename(safe_path))  # 🔹 Actualiza M3U al añadir

    return redirect(url_for('file_manager', path=path))


@app.route('/download/<path:path>')
def download_file(path):
    full_path = os.path.join(BASE_DIR, path)
    if os.path.exists(full_path):
        return send_file(full_path, as_attachment=True)
    return "Archivo no encontrado", 404


@app.route('/delete_file', methods=['POST'])
def delete_file():
    path = request.args.get('path')
    if not path:
        return jsonify(success=False, error="No se especificó una ruta"), 400

    full_path = os.path.join(BASE_DIR, os.path.normpath(path))
    folder = os.path.dirname(full_path)
    filename = os.path.basename(full_path)

    try:
        if os.path.exists(full_path):
            if os.path.isfile(full_path):
                os.remove(full_path)
                update_m3u_on_delete(folder, filename)  # 🔹 Actualiza M3U al borrar
                return jsonify(success=True)
            elif os.path.isdir(full_path):
                shutil.rmtree(full_path)
                return jsonify(success=True)
            else:
                return jsonify(success=False, error="No es un archivo ni un directorio"), 400
        else:
            return jsonify(success=False, error="El archivo o directorio no existe"), 404
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

def get_default_volume():
    try:
        with open(VOLUME_FILE, 'r') as f:
            for line in f:
                m = re.search(r'\["default-volume"\]\s*=\s*([0-9.]+)', line)
                if m:
                    return float(m.group(1))
    except Exception:
        pass
    return 0.4  # valor por defecto si falla

@app.route('/set_volume', methods=['POST'])
def set_volume():
    try:
        vol = float(request.form.get("volume", 0.4))
        if not 0.0 <= vol <= 1.0:
            return jsonify(success=False, error="Valor fuera de rango"), 400

        # Ejecutar script con sudo para modificar archivo
        subprocess.run(["sudo", "/home/radiobit/stream/set_volume.sh", str(vol)], check=True)

        return jsonify(success=True, volume=vol)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2140, debug=True)
