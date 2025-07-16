from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
from pathlib import Path
import subprocess
import psutil

# ==============================================================================
#                      CẤU HÌNH CHUNG (HÃY THAY ĐỔI CÁC THÔNG SỐ NÀY)
# ==============================================================================
CHROME_DEBUG_PORT = 9222
UPLOAD_FOLDER = Path(r"D:\Cos.tv\Videoupload")
PUBLISH_VIDEO_URL = "https://cos.tv/v2/studio/publish-video"
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')
NUMBER_OF_UPLOAD_TABS = 10
MAX_VIDEOS_TO_UPLOAD = 250

# Cấu hình thời gian chờ
TIME_AFTER_EACH_FILE_SEND = 3 # Giây: Chờ sau khi send_keys cho mỗi file
TIME_AFTER_ALL_FILES_SENT = 5 # Giây: Chờ sau khi TẤT CẢ các file trong lô đã được gửi

# Đường dẫn đến tệp thực thi Chrome của bạn
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# Đường dẫn đến thư mục profile người dùng của Chrome
CHROME_USER_DATA_DIR = r"C:\Users\Admin\AppData\Local\Google\Chrome\User Data\Profile1"

# Cập nhật URL đăng nhập và URL chuyển hướng sau khi chưa đăng nhập
LOGIN_URL = "https://cos.tv/v2/welcome/sign-in" # URL của trang đăng nhập chính
LOGIN_REDIRECT_URL_PARTIAL = "/v2/welcome/sign-in?continue=" # Phần của URL khi chuyển hướng đến trang đăng nhập


# Selector của các phần tử
SELECTORS = {
    "file_input": "input[type='file']",
    "description_textarea": "/html/body/div[1]/div/div/div/div[1]/main/div/div[1]/div/form/div/div/div[2]/div/div[2]/div/div[1]/div[1]/textarea",
    "category_dropdown_button": "i.mdi-menu-down",
    "game_category_option": "//div[contains(@class, 'v-list-item__title') and text()='Trò chơi']",
    "thumbnail_selector": ".pa-1:nth-child(1) .v-responsive__content",
    "publish_button": "button.v-btn--is-elevated",
}

# Danh sách để theo dõi các video đã được xử lý
processed_video_paths = []

# ==============================================================================
#                      HÀM HỖ TRỢ
# ==============================================================================

def is_chrome_running_on_port(port):
    """Kiểm tra xem Chrome có đang chạy và lắng nghe trên cổng gỡ lỗi cụ thể không."""
    for conn in psutil.net_connections(kind='inet'):
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
            try:
                process = psutil.Process(conn.pid)
                if 'chrome' in process.name().lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return False

def check_and_handle_login(driver_instance: webdriver.Chrome, url_to_check: str):
    """
    Kiểm tra trạng thái đăng nhập dựa trên sự thay đổi URL.
    Nếu chưa đăng nhập, tạm dừng và yêu cầu đăng nhập thủ công.
    Args:
        driver_instance: Đối tượng WebDriver.
        url_to_check: URL mà script mong muốn ở đó nếu đã đăng nhập (ví dụ: PUBLISH_VIDEO_URL).
    Returns:
        True nếu đã đăng nhập hoặc người dùng đã đăng nhập thủ công thành công, False nếu không thể tiếp tục.
    """
    log_message("Đang kiểm tra trạng thái đăng nhập...")
    driver_instance.get(url_to_check)
    time.sleep(3) # Chờ trang tải đầy đủ để kiểm tra

    # Kiểm tra URL: nếu nó bị thay đổi thành URL đăng nhập thì tức là chưa đăng nhập
    current_url_lower = driver_instance.current_url.lower()
    if LOGIN_REDIRECT_URL_PARTIAL in current_url_lower or \
       current_url_lower.strip('/') == LOGIN_URL.strip('/'):
        log_message(f"Phát hiện trang đăng nhập! URL hiện tại: {driver_instance.current_url}")
        log_message(f"Vui lòng ĐĂNG NHẬP THỦ CÔNG trong cửa sổ Chrome vừa mở.")
        log_message(f"Sau khi đăng nhập thành công và trang {url_to_check} hiện ra, NHẤN ENTER trong cửa sổ console này để tiếp tục.")
        try:
            input("Nhấn Enter để tiếp tục...")
            driver_instance.get(url_to_check) # Tải lại trang sau khi người dùng đăng nhập
            # Chờ URL mục tiêu xuất hiện, hoặc một phần tử sau đăng nhập
            WebDriverWait(driver_instance, 60).until(EC.url_to_be(url_to_check)) # Tăng thời gian chờ cho việc đăng nhập
            log_message("Đã xác nhận đăng nhập thành công.")
            return True
        except Exception as e:
            log_message(f"Lỗi khi chờ người dùng đăng nhập hoặc URL không đúng sau đăng nhập: {e}", "ERROR")
            return False
    else:
        log_message("Đã đăng nhập. Tiếp tục quy trình.")
        return True


def get_next_videos_for_upload(count):
    """
    Lấy 'count' video chưa được xử lý từ thư mục upload.
    Sắp xếp theo tên file để có thứ tự ổn định.
    """
    all_files_in_folder = [f for f in UPLOAD_FOLDER.iterdir() if f.is_file()]

    available_videos = [f for f in all_files_in_folder
                        if f.suffix.lower() in VIDEO_EXTENSIONS and str(f) not in processed_video_paths]

    if not available_videos:
        print(f"[{time.strftime('%H:%M:%S')}] Không còn video nào để tải lên trong thư mục '{UPLOAD_FOLDER}'.")
        return []

    available_videos.sort()
    return available_videos[:count]

def generate_video_details(video_path: Path):
    """Tạo mô tả từ đường dẫn video."""
    base_name_without_ext = video_path.stem

    description = (
                f"Chúc bạn xem vui vẻ!"
    )
    return description

def log_message(message, level="INFO"):
    """Hàm hỗ trợ ghi log với timestamp và mức độ."""
    print(f"[{time.strftime('%H:%M:%S')}] {level}: {message}")

# ==============================================================================
#                      KHỞI TẠO TRÌNH DUYỆT VÀ VÒNG LẶP CHÍNH
# ==============================================================================
driver = None
chrome_process = None
try:
    # --- KIỂM TRA VÀ KHỞI CHẠY CHROME NẾU CHƯA CÓ ---
    if not is_chrome_running_on_port(CHROME_DEBUG_PORT):
        log_message(f"Không tìm thấy Chrome đang chạy trên cổng {CHROME_DEBUG_PORT}. Đang khởi chạy Chrome...")
        chrome_command = [
            CHROME_PATH,
            f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            f"--user-data-dir={CHROME_USER_DATA_DIR}",
            # "--start-maximized"
        ]
        chrome_process = subprocess.Popen(chrome_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_message("Đã khởi chạy Chrome. Chờ vài giây để Chrome sẵn sàng...")
        time.sleep(5)
    else:
        log_message(f"Tìm thấy Chrome đang chạy trên cổng {CHROME_DEBUG_PORT}. Đang kết nối đến phiên hiện có.")

    # --- KẾT NỐI SELENIUM ĐẾN CHROME ---
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{CHROME_DEBUG_PORT}")

    driver = webdriver.Chrome(options=chrome_options)
    log_message("Đã kết nối thành công đến trình duyệt Chrome đang mở!")

    # Lưu lại handle của cửa sổ chính ngay sau khi kết nối,
    # đảm bảo đây là cửa sổ mà script sẽ quay lại.
    main_window_handle = driver.current_window_handle
    log_message(f"Tiêu đề của tab chính: {driver.title}")

    # --- KIỂM TRA ĐĂNG NHẬP BAN ĐẦU (MỘT LẦN DUY NHẤT) ---
    # Luôn kiểm tra trên tab chính
    if not check_and_handle_login(driver, PUBLISH_VIDEO_URL):
        log_message("Không thể đăng nhập hoặc người dùng đã hủy. Dừng chương trình.", "CRITICAL")
        exit() # Dừng toàn bộ script nếu không đăng nhập được

    uploaded_total_count = 0
    batch_number = 0

    while uploaded_total_count < MAX_VIDEOS_TO_UPLOAD:
        batch_number += 1
        log_message(f"\n======== BẮT ĐẦU LÔ TẢI LÊN SỐ {batch_number} (lặp lại {batch_number}/25) ========")

        videos_for_this_batch = get_next_videos_for_upload(NUMBER_OF_UPLOAD_TABS)

        if not videos_for_this_batch:
            log_message("Đã hết video trong thư mục hoặc đã đạt số lượng tối đa mong muốn. Dừng chương trình.")
            break

        log_message(f"Lô này sẽ xử lý {len(videos_for_this_batch)} video.")

        upload_tab_handles = []
        video_details_map = {}

        # --- BƯỚC 1: Mở các tab phụ và điều hướng URL ---
        log_message(f"\n--- Giai đoạn 1: Đang mở {len(videos_for_this_batch)} tab phụ và điều hướng đến URL tải video ---")
        for i in range(len(videos_for_this_batch)):
            driver.switch_to.new_window('tab')
            current_handle = driver.current_window_handle
            upload_tab_handles.append(current_handle)
            log_message(f"Đã mở tab phụ thứ {i+1} (handle: {current_handle[:8]}...).")
            driver.get(PUBLISH_VIDEO_URL)
            time.sleep(1) # Cho tab một chút thời gian để tải trang

        driver.switch_to.window(main_window_handle)
        log_message("Đã mở tất cả các tab phụ và quay lại tab chính.")


        # --- BƯỚC 2 (PHẦN 1): Trên từng tab phụ, gửi file video ---
        log_message("\n--- Giai đoạn 2 (Phần 1): Đang gửi file video trên các tab phụ ---")
        for i, handle in enumerate(upload_tab_handles):
            if i >= len(videos_for_this_batch):
                log_message(f"Không đủ video cho tất cả {NUMBER_OF_UPLOAD_TABS} tab. Chỉ xử lý {len(videos_for_this_batch)} video trong lô này.", "WARN")
                break

            driver.switch_to.window(handle)
            video_path = videos_for_this_batch[i]
            description_content = generate_video_details(video_path)
            video_details_map[handle] = (video_path, description_content)

            log_message(f"Đang xử lý gửi file cho video: {video_path.name} trong tab {i+1}/{len(upload_tab_handles)}")

            try:
                # Không cần kiểm tra đăng nhập lặp lại ở đây, vì đã xử lý ở đầu script.
                # Nếu phiên hết hạn trong quá trình này, Selenium sẽ gặp lỗi khi tìm các phần tử.
                file_input_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["file_input"]))
                )
                file_input_element.send_keys(str(video_path))
                log_message(f"Đã chỉ định tệp tin: {video_path.name} (qua input[type=file]).")

                log_message(f"Chờ {TIME_AFTER_EACH_FILE_SEND} giây sau khi gửi file cho tab {i+1}...")
                time.sleep(TIME_AFTER_EACH_FILE_SEND)

            except Exception as e_send_file:
                log_message(f"LỖI khi gửi file video '{video_path.name}' trong tab {i+1}: {e_send_file}", "ERROR")
                log_message("Video này sẽ được bỏ qua trong lô hiện tại.", "WARN")
                if handle in upload_tab_handles:
                    upload_tab_handles.remove(handle)
                if handle in video_details_map:
                    del video_details_map[handle]
                continue

        log_message(f"\nĐã gửi file cho tất cả các tab. Chờ {TIME_AFTER_ALL_FILES_SENT} giây cho tất cả các tab xử lý...")
        time.sleep(TIME_AFTER_ALL_FILES_SENT)


        # --- BƯỚC 2 (PHẦN 2): Quay lại từng tab để điền chi tiết và xuất bản ---
        log_message("\n--- Giai đoạn 2 (Phần 2): Đang điền chi tiết và xuất bản trên các tab ---")
        successful_uploads_in_batch = 0
        for i, handle in enumerate(upload_tab_handles):
            if handle not in video_details_map:
                continue

            driver.switch_to.window(handle)
            video_path, description_content = video_details_map[handle]

            log_message(f"Đang điền chi tiết và xuất bản cho video: {video_path.name} trong tab {i+1}/{len(upload_tab_handles)}")

            try:
                wait = WebDriverWait(driver, 30)

                # 1. Bỏ qua điền TIÊU ĐỀ vì COS.TV tự động nhận.

                # 2. Điền MÔ TẢ
                description_textarea = wait.until(EC.presence_of_element_located((By.XPATH, SELECTORS["description_textarea"])))
                description_textarea.clear()
                description_textarea.send_keys(description_content)
                log_message("Đã điền nội dung mô tả.")

                # 3. NHẤP NÚT CUỘN XUỐNG (dropdown category/tags)
                scroll_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTORS["category_dropdown_button"])))
                scroll_button.click()
                log_message("Đã nhấp vào nút cuộn xuống (dropdown category/tags).")
                time.sleep(1)

                # 4. NHẤP VÀO LỰA CHỌN "Trò chơi" (được coi là điền tags/category)
                game_category_option = wait.until(EC.element_to_be_clickable((By.XPATH, SELECTORS["game_category_option"])))
                game_category_option.click()
                log_message("Đã nhấp vào lựa chọn 'Trò chơi'.")
                time.sleep(1)

                # 5. NHẤP VÀO Thumbnail
                thumbnail_element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTORS["thumbnail_selector"])))
                thumbnail_element.click()
                log_message("Đã nhấp vào Thumbnail.")
                time.sleep(1)

                # 6. NHẤP VÀO NÚT PUBLISH/UPLOAD CUỐI CÙNG
                publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTORS["publish_button"])))
                publish_button.click()
                log_message("Đã nhấp vào nút Publish/Upload. Chờ xác nhận...")
                time.sleep(5) # TODO: Cần CƠ CHẾ CHỜ XÁC NHẬN CỤ THỂ HƠN

                processed_video_paths.append(str(video_path))
                uploaded_total_count += 1
                successful_uploads_in_batch += 1
                log_message(f"Video '{video_path.name}' đã được xử lý và xuất bản thành công!")

            except Exception as e_process_details:
                log_message(f"LỖI khi điền chi tiết hoặc xuất bản video '{video_path.name}' trong tab {i+1}: {e_process_details}", "ERROR")
                log_message("Video này sẽ được bỏ qua và không được tính là đã tải lên thành công.", "WARN")

        # --- BƯỚC 3: Đóng các tab phụ và quay về tab chính ---
        log_message("\n--- Giai đoạn 3: Đang đóng các tab phụ và quay về tab chính ---")
        for handle in upload_tab_handles:
            try:
                driver.switch_to.window(handle)
                driver.close()
                log_message(f"Đã đóng tab phụ (handle: {handle[:8]}...).")
            except Exception as e_close:
                log_message(f"Không thể đóng tab phụ (handle: {handle[:8]}...): {e_close}", "ERROR")

        driver.switch_to.window(main_window_handle)
        log_message("Đã đóng tất cả các tab phụ và quay lại tab chính.")

        # --- BƯỚC 5: Xóa các video đã tải lên khỏi thư mục nguồn ---
        log_message("\n--- Giai đoạn 5: Đang xóa các video đã tải lên khỏi thư mục nguồn ---")
        videos_to_delete_in_this_batch = [Path(p) for p in processed_video_paths[-successful_uploads_in_batch:]]

        for video_path_to_delete in videos_to_delete_in_this_batch:
            try:
                if video_path_to_delete.exists():
                    os.remove(video_path_to_delete)
                    log_message(f"Đã xóa: {video_path_to_delete.name}")
            except Exception as e_delete:
                log_message(f"Không thể xóa tệp '{video_path_to_delete.name}': {e_delete}", "ERROR")
                log_message("Vui lòng kiểm tra quyền truy cập file. Có thể file đang bị chương trình khác chiếm giữ.", "WARN")

        log_message(f"\nTỔNG SỐ VIDEO ĐÃ TẢI LÊN VÀ XỬ LÝ THÀNH CÔNG: {uploaded_total_count}/{MAX_VIDEOS_TO_UPLOAD}")

        # --- BƯỚC 4: Kiểm tra và lặp lại vòng lặp ---
        if uploaded_total_count >= MAX_VIDEOS_TO_UPLOAD:
            log_message("Đã đạt số lượng video tối đa mong muốn. Dừng chương trình.")
            break

        log_message(f"Chờ 10 giây trước khi bắt đầu lô tải lên tiếp theo để tránh bị chặn...")
        time.sleep(10)

except Exception as e:
    log_message(f"ĐÃ XẢY RA LỖI CHUNG KHÔNG MONG UỐN: {e}", "CRITICAL")
    import traceback
    traceback.print_exc()

finally:
    log_message("\n================ CHƯƠNG TRÌNH KẾT THÚC ================")
    if driver:
        try:
            driver.quit()
            log_message("Đã đóng tất cả các cửa sổ/tab của trình duyệt Selenium.")
        except Exception as e_quit_driver:
            log_message(f"Lỗi khi đóng driver Selenium: {e_quit_driver}", "ERROR")

    if chrome_process:
        try:
            chrome_process.terminate()
            chrome_process.wait(timeout=5)
            if chrome_process.poll() is None:
                chrome_process.kill()
                log_message("Đã ép buộc đóng tiến trình Chrome.", "WARN")
            log_message("Đã đóng tiến trình Chrome được khởi chạy bởi script.")
        except Exception as e_kill_chrome:
            log_message(f"Lỗi khi đóng tiến trình Chrome: {e_kill_chrome}", "ERROR")
    
    log_message("Script đã hoàn tất.")