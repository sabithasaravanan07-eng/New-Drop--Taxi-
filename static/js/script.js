document.addEventListener("DOMContentLoaded", function () {
  const navToggle = document.querySelector(".nav-toggle");
  const navLinks = document.querySelector(".nav-links");
  if (navToggle && navLinks) {
    navToggle.style.display = "none";
    navLinks.classList.remove("open");
  }

  const menuBtn = document.querySelector(".admin-menu-btn");
  const sidebar = document.querySelector(".admin-sidebar");
  if (menuBtn && sidebar) {
    menuBtn.addEventListener("click", () => sidebar.classList.toggle("open"));
  }

  document.querySelectorAll(".alert[data-autohide]").forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity .4s ease";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 450);
    }, 4000);
  });

  const starWrap = document.querySelector(".star-select");
  if (starWrap) {
    const stars = starWrap.querySelectorAll("i");
    const ratingInput = document.getElementById("rating");
    const setStars = (value) => {
      stars.forEach((star) => {
        star.classList.toggle("active", parseInt(star.dataset.val, 10) <= value);
      });
    };
    stars.forEach((star) => {
      star.addEventListener("click", () => {
        const value = parseInt(star.dataset.val, 10);
        ratingInput.value = value;
        setStars(value);
      });
    });
    setStars(parseInt(ratingInput.value || "5", 10));
  }

  const dateField = document.getElementById("pickup_date");
  if (dateField) {
    dateField.setAttribute("min", new Date().toISOString().split("T")[0]);
  }

  const tripType = document.getElementById("trip_type");
  const returnWrap = document.getElementById("return_date_wrap");
  if (tripType && returnWrap) {
    const syncReturnDate = () => {
      returnWrap.style.display = tripType.value === "round_trip" ? "block" : "none";
    };
    tripType.addEventListener("change", syncReturnDate);
    syncReturnDate();
  }

  document.querySelectorAll("form[data-validate]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      let valid = true;
      form.querySelectorAll("[required]").forEach((field) => {
        const empty = !field.value || !field.value.trim();
        field.style.borderColor = empty ? "#B54A34" : "";
        valid = valid && !empty;
      });
      if (!valid) {
        event.preventDefault();
        let message = form.querySelector(".js-validate-msg");
        if (!message) {
          message = document.createElement("div");
          message.className = "alert alert-error js-validate-msg";
          message.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Please fill in all required fields.';
          form.prepend(message);
        }
      }
    });
  });

  const scrollTopBtn = document.querySelector(".scroll-top");
  if (scrollTopBtn) {
    scrollTopBtn.addEventListener("click", (event) => {
      event.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm || "Are you sure?")) {
        event.preventDefault();
      }
    });
  });

  const path = window.location.pathname;
  document.querySelectorAll(".nav-links a").forEach((link) => {
    if (link.getAttribute("href") === path) link.classList.add("active");
  });
});
