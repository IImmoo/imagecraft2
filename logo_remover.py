import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
from rembg import remove
import os

class LogoRemoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Logo Kaldırma Uygulaması")
        self.root.geometry("800x600")

        # Ana çerçeve
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Butonlar
        self.select_btn = tk.Button(self.main_frame, text="Fotoğraf Seç", command=self.select_image)
        self.select_btn.pack(pady=5)

        self.process_btn = tk.Button(self.main_frame, text="Logoyu Kaldır", command=self.remove_logo)
        self.process_btn.pack(pady=5)
        self.process_btn.config(state=tk.DISABLED)

        self.save_btn = tk.Button(self.main_frame, text="Kaydet", command=self.save_image)
        self.save_btn.pack(pady=5)
        self.save_btn.config(state=tk.DISABLED)

        # Görüntü alanı
        self.image_frame = tk.Frame(self.main_frame)
        self.image_frame.pack(fill=tk.BOTH, expand=True)

        self.original_label = tk.Label(self.image_frame, text="Orijinal Görüntü")
        self.original_label.grid(row=0, column=0)

        self.processed_label = tk.Label(self.image_frame, text="İşlenmiş Görüntü")
        self.processed_label.grid(row=0, column=1)

        self.original_image_label = tk.Label(self.image_frame)
        self.original_image_label.grid(row=1, column=0, padx=5)

        self.processed_image_label = tk.Label(self.image_frame)
        self.processed_image_label.grid(row=1, column=1, padx=5)

        self.image_path = None
        self.processed_image = None

    def select_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff")]
        )
        if file_path:
            self.image_path = file_path
            self.show_original_image()
            self.process_btn.config(state=tk.NORMAL)

    def show_original_image(self):
        image = Image.open(self.image_path)
        image.thumbnail((350, 350))
        photo = ImageTk.PhotoImage(image)
        self.original_image_label.config(image=photo)
        self.original_image_label.image = photo

    def remove_logo(self):
        if self.image_path:
            # Görüntüyü yükle
            img = cv2.imread(self.image_path)
            
            # Arka plan kaldırma işlemi
            output = remove(img)
            
            # Alfa kanalını kaldır ve beyaz arka plan ekle
            if output.shape[2] == 4:  # RGBA format
                alpha = output[:, :, 3] / 255.0
                output_rgb = output[:, :, :3]
                white_bg = np.ones_like(output_rgb) * 255
                output_final = (alpha[:, :, np.newaxis] * output_rgb + 
                              (1 - alpha[:, :, np.newaxis]) * white_bg).astype(np.uint8)
            else:
                output_final = output

            self.processed_image = output_final
            
            # İşlenmiş görüntüyü göster
            processed_pil = Image.fromarray(cv2.cvtColor(output_final, cv2.COLOR_BGR2RGB))
            processed_pil.thumbnail((350, 350))
            photo = ImageTk.PhotoImage(processed_pil)
            self.processed_image_label.config(image=photo)
            self.processed_image_label.image = photo
            
            self.save_btn.config(state=tk.NORMAL)

    def save_image(self):
        if self.processed_image is not None:
            save_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg")]
            )
            if save_path:
                cv2.imwrite(save_path, self.processed_image)
                messagebox.showinfo("Başarılı", "Görüntü başarıyla kaydedildi!")

if __name__ == "__main__":
    root = tk.Tk()
    app = LogoRemoverApp(root)
    root.mainloop() 