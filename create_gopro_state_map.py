import re
from bs4 import BeautifulSoup

def parse_html_tables(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    mappings = {}
    
    sections = soup.find_all('section')
    for section in sections:
        h3 = section.find('h3')
        if not h3:
            continue
        
        match = re.match(r'(.+?)\s*\((\d+)\)', h3.text.strip())
        if not match:
            continue
            
        name, section_id = match.groups()
        section_id = int(section_id)
        
        mappings[section_id] = {'name': name.strip(), 'values': {}}
        
        table = section.find('table')
        if not table:
            continue

        for row in table.find_all('tr')[1:]:  # Skip header row
            cells = row.find_all('td')
            if len(cells) >= 2:
                id_text = cells[0].text.strip()
                try:
                    value_id = int(id_text)
                    value_name = cells[1].text.strip()
                    mappings[section_id]['values'][value_id] = value_name
                except ValueError:
                    pass # Ignore non-integer IDs
    return mappings

def generate_enums_class(settings_map, statuses_map):
    class_str = "class GoProEnums:\n"
    
    # STATUS_NAMES
    class_str += "    STATUS_NAMES = {\n"
    for sid, data in sorted(statuses_map.items()):
        class_str += f"        {sid}: \"{data['name']}\",\n"
    class_str += "    }\n\n"
    
    # STATUS_VALUES
    class_str += "    STATUS_VALUES = {\n"
    for sid, data in sorted(statuses_map.items()):
        if data['values']:
            class_str += f"        {sid}: {{\n"
            for vid, vname in sorted(data['values'].items()):
                class_str += "            {}: \"{}\",\n".format(vid, vname.replace('"', '\\"'))
            class_str += "        },\n"
    class_str += "    }\n\n"

    # SETTING_NAMES
    class_str += "    SETTING_NAMES = {\n"
    for sid, data in sorted(settings_map.items()):
        class_str += f"        {sid}: \"{data['name']}\",\n"
    class_str += "    }\n\n"

    # SETTING_VALUES
    class_str += "    SETTING_VALUES = {\n"
    for sid, data in sorted(settings_map.items()):
        if data['values']:
            class_str += f"        {sid}: {{\n"
            for vid, vname in sorted(data['values'].items()):
                class_str += "            {}: \"{}\",\n".format(vid, vname.replace('"', '\\"'))
            class_str += "        },\n"
    class_str += "    }\n"
    
    return class_str

def main():
    # https://gopro.github.io/OpenGoPro/ble/features/settings.html
    with open('/srv/fenetre.cam/tmp/settings.html', 'r') as f:
        settings_html = f.read()
    # https://gopro.github.io/OpenGoPro/ble/features/statuses.html
    with open('/srv/fenetre.cam/tmp/statuses.html', 'r') as f:
        statuses_html = f.read()

    settings_map = parse_html_tables(settings_html)
    statuses_map = parse_html_tables(statuses_html)
    
    new_enums_class = generate_enums_class(settings_map, statuses_map)

    with open('/srv/fenetre.cam/gopro_state_map.py', 'w') as f:
        f.write(new_enums_class)

if __name__ == "__main__":
    main()
