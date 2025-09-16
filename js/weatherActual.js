async function getWeather() {
  const city = document.getElementById('city').value;
  const url = `https://wttr.in/${city}?format=%C+%t+%w`;
  
  try {
      const response = await fetch(url);
      const data = await response.text();
      const [condition, temp, wind] = data.split(' ');
      document.getElementById('weather').innerHTML = `
          <h2>${city}</h2>
          <p>Состояние: ${condition}</p>
          <p>Температура: ${temp}</p>
          <p>Ветер: ${wind}</p>
      `;
  } catch (error) {
      document.getElementById('weather').innerHTML = '<p>Ошибка получения данных</p>';
  }
}