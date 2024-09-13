import tkinter as tk
from tkinter import ttk


# Custom Combobox class with autocomplete functionality
class tkAutocompleteCombobox(ttk.Combobox):
    def set_completion_list(self, completion_list: list[str]) -> None:
        # Remove duplicates and sort the list
        self._completion_list = sorted(set(completion_list))
        self._hits = []
        self._hit_index = 0
        self.position = 0
        self.bind("<KeyRelease>", self.handle_keyrelease)
        self["values"] = self._completion_list

        # Automatically select the first item in the list
        if self._completion_list:
            self.select_item(self._completion_list[0])

    def autocomplete(self, delta: int = 0) -> None:
        if delta:
            self.delete(self.position, tk.END)
        else:
            self.position = len(self.get())

        # Find matching items
        _hits = [
            item
            for item in self._completion_list
            if item.lower().startswith(self.get().lower())
        ]
        if _hits != self._hits:
            self._hit_index = 0
            self._hits = _hits
        if _hits:
            self._hit_index = (self._hit_index + delta) % len(_hits)
            self.delete(0, tk.END)
            self.insert(0, _hits[self._hit_index])
            self.select_range(self.position, tk.END)

    def select_item(self, item: str) -> None:
        self.set(item)
        self.event_generate("<<ComboboxSelected>>")  # Notify main function

    def handle_keyrelease(self, event):
        # Ignore certain keys
        if event.keysym in ("BackSpace", "Left", "Right", "Up", "Down"):
            return

        # Add new item if Enter is pressed and item is not in the list
        if event.keysym == "Return":
            new_item = self.get()
            if new_item not in self._completion_list:
                self._completion_list.append(new_item)
                self.set_completion_list(self._completion_list)
            self.select_item(new_item)

        self.autocomplete()


def main():
    # Create the main window
    root = tk.Tk()
    root.geometry("300x250")

    # Create and pack the output box with legend
    output_label = tk.Label(root, text="Selected Item:")
    output_label.pack()
    output_box = tk.Text(root, height=1, width=20)
    output_box.pack()

    # Create and pack the AutocompleteCombobox
    combo = tkAutocompleteCombobox(root)
    combo.set_completion_list(["apple", "banana", "cherry", "date"])
    combo.pack(pady=20)

    # Function to update the output box with the selected item
    def update_output(event):
        selected_item = combo.get()
        output_box.delete(1.0, tk.END)
        output_box.insert(tk.END, selected_item)

    # Bind the selection event to the update_output function
    combo.bind("<<ComboboxSelected>>", update_output)

    # Run the application
    root.mainloop()


if __name__ == "__main__":
    main()
