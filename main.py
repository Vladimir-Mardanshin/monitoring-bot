import datetime
import time
import firebase_admin
from firebase_admin import credentials, db
import telebot
from telebot import types
import requests

TOKEN = '7004875202:AAHN-7VB4MwN0PrCuwWKpPVNsuZcieUh8AM'
time_sleep = 20
bot = telebot.TeleBot(TOKEN)
prometheus_url = "http://192.168.0.114:9090"
firebase_admin.initialize_app(credentials.Certificate("fire.json"),
                              {'databaseURL': 'https://monitoring-db-a0727-default-rtdb.firebaseio.com/'})


def parse_metrics(url):
    response = requests.get(url)
    metrics = response.text.split('\n')

    parsed_metrics = {}
    for metric in metrics:
        if not metric.startswith('#') and metric.strip():
            parts = metric.split()
            key = parts[0]
            value = parts[1]
            parsed_metrics[key] = value

    return parsed_metrics


def get_specific_metric(metrics, metric_name):
    return metrics.get(metric_name, None)


def get_used_ram(metrics):
    mem_available = float(get_specific_metric(metrics, "node_memory_MemAvailable_bytes"))
    mem_total = float(get_specific_metric(metrics, "node_memory_MemTotal_bytes"))
    return (1 - (mem_available / mem_total)) * 100


def count_cpu_cores(metrics):
    cpu_cores = set()
    for metric in metrics.keys():
        if metric.startswith("node_cpu_seconds_total{"):
            cpu_core = metric.split("{")[1].split(",")[0].split("=")[1]
            cpu_cores.add(cpu_core)

    return len(cpu_cores)


def get_time_system(metrics):
    time_seconds = float(get_specific_metric(metrics, "node_time_seconds"))
    boot_time_seconds = float(get_specific_metric(metrics, "node_boot_time_seconds"))
    return (time_seconds - boot_time_seconds) / 3600


def get_size_system(metrics):
    return float(get_specific_metric(metrics, 'node_filesystem_size_bytes{device="/dev/mapper/ubuntu--vg-ubuntu--lv",'
                                              'fstype="ext4",mountpoint="/"}')) / 1024 / 1024 / 1024


def get_total_ram(metrics):
    return float(get_specific_metric(metrics, 'node_memory_MemTotal_bytes')) / 1024 / 1024 / 1024


def get_total_swap(metrics):
    return float(get_specific_metric(metrics, 'node_memory_SwapTotal_bytes')) / 1024 / 1024 / 1024


def get_root_fs_used(metrics):
    filesystem_avail = float(get_specific_metric(metrics, 'node_filesystem_avail_bytes{'
                                                          'device="/dev/mapper/ubuntu--vg-ubuntu--lv",fstype="ext4",'
                                                          'mountpoint="/"}'))
    filesystem_size = float(get_specific_metric(metrics, 'node_filesystem_size_bytes{'
                                                         'device="/dev/mapper/ubuntu--vg-ubuntu--lv",fstype="ext4",'
                                                         'mountpoint="/"}'))
    return 100 - ((filesystem_avail * 100) / filesystem_size)


def get_swap_used(metrics):
    swap_total = float(get_specific_metric(metrics, 'node_memory_SwapTotal_bytes'))
    swap_free = float(get_specific_metric(metrics, 'node_memory_SwapFree_bytes'))

    if swap_total < 0.1:
        return 0
    else:
        return ((swap_total - swap_free) / swap_total) * 100


def get_sys_load(metrics):
    node_load1 = float(get_specific_metric(metrics, 'node_load1'))
    return (node_load1 * 100) / count_cpu_cores(metrics)


def view_node(message, url):
    metrics = parse_metrics(url)

    text = f"Нагрузка на систему: {round(get_sys_load(metrics), 1)}%\n"
    text += f"Использование RAM: {round(get_used_ram(metrics), 1)}%\n"
    text += f"Использование подкачки: {round(get_swap_used(metrics), 1)}%\n"
    text += f"Используемый объем диска: {round(get_root_fs_used(metrics), 1)}%\n"
    text += f"Количество ядер процессора: {count_cpu_cores(metrics)}\n"
    text += f"Система запущена {round(get_time_system(metrics), 1)} часов назад\n"
    text += f"Общий объем диска: {round(get_size_system(metrics), 1)} Гб\n"
    text += f"Общий размер RAM: {round(get_total_ram(metrics), 1)} Гб\n"
    text += f"Объем файла подкачки: {round(get_total_swap(metrics), 1)} Гб\n"

    markup = types.InlineKeyboardMarkup()
    button1 = types.InlineKeyboardButton("Назад", callback_data=f'back_click_{url}')
    markup.add(button1)
    bot.send_message(message.chat.id, text, reply_markup=markup)


check = False


def specific_node(message, node_exporter_url, prev_message_id):
    global check, check_specific_function
    check = True
    while True:
        check_specific_function = True
        if not check:
            check_specific_function = False
            return

        text = check_system(node_exporter_url)

        if text != "":

            try:
                bot.delete_message(message.chat.id, prev_message_id)
            except telebot.apihelper.ApiTelegramException:
                check_specific_function = False
                return

            add_fire(text, get_target_name_by_address(get_targets_dict(), node_exporter_url))

            markup1 = types.InlineKeyboardMarkup()
            button1 = types.InlineKeyboardButton("Отключить уведомления",
                                                 callback_data=f'change_not_{node_exporter_url}')
            markup1.add(button1)
            new_message = bot.send_message(message.chat.id, text, reply_markup=markup1)
            prev_message_id = new_message.id
            time.sleep(50)

        time.sleep(0)
        check_specific_function = False


def look_notifications_day(message, url):
    now = datetime.datetime.now()
    current_date = now.strftime('%d.%m.%Y')

    notification_ref = db.reference('Notification')
    notification_data = notification_ref.get()

    text = ""
    if notification_data is not None:
        for key, value in notification_data.items():
            if (value.get('date') == current_date and
                    value.get('node') == get_target_name_by_address(get_targets_dict(), url)):
                text += f"{value.get('time')}\n"
                text += f"{value.get('notification')}\n"

    if text != "":
        markup = types.InlineKeyboardMarkup()
        button1 = types.InlineKeyboardButton("Назад", callback_data=f'back_click_{url}')
        markup.add(button1)
        bot.send_message(message.chat.id, text, reply_markup=markup)
    else:
        markup = types.InlineKeyboardMarkup()
        button1 = types.InlineKeyboardButton("Назад", callback_data=f'back_click_{url}')
        markup.add(button1)
        bot.send_message(message.chat.id, "Уведомлений нет!", reply_markup=markup)


def send_actions_message(chat_id, url):
    markup = types.InlineKeyboardMarkup()
    try:
        requests.get(url, timeout=5)
    except requests.exceptions.ConnectTimeout:
        button = types.InlineKeyboardButton("Назад", callback_data=f'back_start')
        markup.add(button)
        bot.send_message(chat_id, "Узел недоступен!", reply_markup=markup)
        return
    except requests.exceptions.RequestException as e:
        button = types.InlineKeyboardButton("Назад", callback_data=f'back_start')
        markup.add(button)
        bot.send_message(chat_id, f"Произошла ошибка: {e}", reply_markup=markup)
        return

    button1 = types.InlineKeyboardButton("Просмотр данных об узле", callback_data=f'view_node_data_{url}')
    button2 = types.InlineKeyboardButton("Включение уведомлений", callback_data=f'enable_notifications_{url}')
    button3 = types.InlineKeyboardButton("Просмотр уведомлений за день", callback_data=f'notifications_day_{url}')
    button4 = types.InlineKeyboardButton("Поменять узел", callback_data='back_start')
    markup.add(button1)
    markup.add(button2)
    markup.add(button3)
    markup.add(button4)
    bot.send_message(chat_id, f"Узел: {get_target_name_by_address(get_targets_dict(), url)}\nВыберите действие:",
                     reply_markup=markup)


def get_target_name_by_address(targets_dict, address):
    for name, addr in targets_dict.items():
        if addr == address:
            return name
    return None


def get_targets_dict():
    response = requests.get(f'{prometheus_url}/api/v1/targets')
    targets_dict = {}
    if response.status_code == 200:
        data = response.json()

        for target in data['data']['activeTargets']:
            full_target_name = target['labels']['job']
            target_address = target['scrapeUrl']

            if full_target_name.startswith('node-exporter-'):
                target_name = full_target_name[len('node-exporter-'):]
            else:
                target_name = full_target_name

            targets_dict[target_name] = target_address

    return targets_dict


def choice_node(message):
    targets_dict = get_targets_dict()

    markup = types.InlineKeyboardMarkup()
    for target_name, target_address in targets_dict.items():
        button = types.InlineKeyboardButton(f"{target_name}", callback_data=f'node_url_{target_address}')
        markup.add(button)
    button = types.InlineKeyboardButton("Отмена", callback_data=f'back_to_start')
    markup.add(button)

    bot.send_message(message.chat.id, "Выберите узел:", reply_markup=markup)


check_all = False
check_all_function = False
check_specific_function = False


def add_fire(text, node_name):
    now = datetime.datetime.now()
    current_date = now.strftime('%d.%m.%Y')
    current_time = now.strftime('%H:%M')

    notification_ref = db.reference('Notification')
    new_notification_data = {
        'notification': f'{text}',
        'date': current_date,
        'time': current_time,
        'node': node_name
    }
    notification_ref.push(new_notification_data)


def all_node(message, prev_message_id):
    global check_all, check_all_function
    check_all = True

    targets_dict = get_targets_dict()

    while True:
        prev_message_id = check_time(message, prev_message_id)
        check_all_function = True
        if not check_all:
            check_all_function = False
            return

        text_all = ""
        for target_name, target_address in targets_dict.items():
            try:
                requests.get(target_address, timeout=3)

                text_node = check_system(target_address)

                if text_node != "":
                    add_fire(text_node, target_name)
                    text_all += f"Узел: {target_name}\n{text_node}\n"

            except requests.exceptions.ConnectTimeout:
                print(f"url: {target_address} - узел недоступен")

        if text_all != "":

            try:
                bot.delete_message(message.chat.id, prev_message_id)
            except telebot.apihelper.ApiTelegramException:
                check_all_function = False
                return

            markup1 = types.InlineKeyboardMarkup()
            button1 = types.InlineKeyboardButton("Отключить уведомления",
                                                 callback_data=f'off_not_all')
            markup1.add(button1)
            new_message = bot.send_message(message.chat.id, text_all, reply_markup=markup1)
            prev_message_id = new_message.id
            time.sleep(50)

        time.sleep(20)
        check_all_function = False


def check_time(message, prev_message_id):
    current_time = datetime.datetime.now()

    if current_time.hour == 12 and current_time.minute == 54:
        bot.delete_message(message.chat.id, prev_message_id)

        markup = types.InlineKeyboardMarkup()
        button = types.InlineKeyboardButton("Принять",
                                            callback_data=f'true_all_not')
        markup.add(button)
        new_message = bot.send_message(message.chat.id, "Система функционирует в нормальном режиме!",
                                       reply_markup=markup)
        prev_message_id = new_message.id

    return prev_message_id


def choice_action(message):
    markup = types.InlineKeyboardMarkup()
    button1 = types.InlineKeyboardButton("Выбрать узел", callback_data=f'choice_node_btn')
    markup.add(button1)
    button2 = types.InlineKeyboardButton("Включить уведомления", callback_data=f'true_all_not')
    markup.add(button2)
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)


def check_system(url):
    text_notification = ""
    metrics = parse_metrics(url)

    sys_load = round(get_sys_load(metrics), 1)
    used_ram = round(get_used_ram(metrics), 1)
    swap_used = round(get_swap_used(metrics), 1)
    root_fs_used = round(get_root_fs_used(metrics), 1)
    print(f"url: {url} - sys_load: {sys_load}, used_ram: {used_ram}, swap_used: {swap_used}, "
          f"root_fs_used: {root_fs_used}")

    if sys_load > 90:
        text_notification += f"Система сильно перегружена! ({sys_load}%)\n"

    if used_ram > 90:
        text_notification += f"Оперативная память сильно загружена! ({used_ram}%)\n"

    if swap_used > 90:
        text_notification += f"Файл подкачки почти заполнен! ({swap_used}%)\n"

    if root_fs_used > 90:
        text_notification += f"Выделенная область памяти почти заполнена! ({root_fs_used}%)\n"

    return text_notification


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.delete_message(message.chat.id, message.message_id)
    bot.send_message(message.chat.id, f"Управление ботом:\n{prometheus_url[:-4]}5000")
    choice_action(message)


@bot.callback_query_handler(func=lambda call: True)
def query_handler(call):
    global check_all

    if call.data.startswith('view_node_data_'):
        url = call.data[15:]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        view_node(call.message, url)

    if call.data.startswith('enable_notifications_'):
        url = call.data[21:]
        bot.delete_message(call.message.chat.id, call.message.message_id)

        global check_specific_function
        check_action = None
        if check_specific_function:
            mes = bot.send_message(call.message.chat.id, "Пожалуйста, подождите...")
            check_action = mes.id
        while check_specific_function:
            time.sleep(5)
        if check_action:
            bot.delete_message(call.message.chat.id, check_action)

        markup = types.InlineKeyboardMarkup()
        button1 = types.InlineKeyboardButton("Отключить уведомления", callback_data=f'change_not_{url}')
        markup.add(button1)
        new_message = bot.send_message(call.message.chat.id, "Уведомления включены...", reply_markup=markup)
        prev_message_id = new_message.id

        specific_node(call.message, url, prev_message_id)

    if call.data.startswith('back_click_'):
        url = call.data[11:]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_actions_message(call.message.chat.id, url)

    if call.data.startswith('change_not_'):
        global check
        check = False
        url = call.data[11:]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_actions_message(call.message.chat.id, url)

    if call.data.startswith('notifications_day_'):
        url = call.data[18:]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        look_notifications_day(call.message, url)

    if call.data.startswith('node_url_'):
        url = call.data[9:]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_actions_message(call.message.chat.id, url)

    if call.data.startswith('back_start'):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        choice_node(call.message)

    if call.data.startswith('choice_node_btn'):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        choice_node(call.message)

    if call.data.startswith('true_all_not'):
        global check_all_function
        check_all = False
        bot.delete_message(call.message.chat.id, call.message.message_id)

        check_action = None
        if check_all_function:
            mes = bot.send_message(call.message.chat.id, "Пожалуйста, подождите...")
            check_action = mes.id
        while check_all_function:
            time.sleep(5)
        if check_action:
            bot.delete_message(call.message.chat.id, check_action)

        markup = types.InlineKeyboardMarkup()
        button1 = types.InlineKeyboardButton("Отключить уведомления", callback_data=f'off_not_all')
        markup.add(button1)
        new_message = bot.send_message(call.message.chat.id, "Уведомления включены...", reply_markup=markup)
        prev_message_id = new_message.id
        all_node(call.message, prev_message_id)

    if call.data.startswith('off_not_all'):
        check_all = False
        bot.delete_message(call.message.chat.id, call.message.message_id)
        choice_action(call.message)

    if call.data.startswith('back_to_start'):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        choice_action(call.message)


bot.polling(none_stop=True)
