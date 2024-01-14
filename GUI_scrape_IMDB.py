import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse
import concurrent.futures
import pandas as pd

# Maximum number of threads that will be spawned
MAX_THREADS = 50

movie_title_arr = []
movie_year_arr = []
movie_genre_arr = []
movie_synopsis_arr =[]
image_url_arr  = []
image_id_arr = []


def download_stories(story_urls):
    threads = min(MAX_THREADS, len(story_urls))
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        executor.map(scrape, story_urls)


def getMovieTitle(header):
    try:
        return header[0].find("a").getText()
    except:
        return 'NA'


def getReleaseYear(header):
    try:
        return header[0].find("span",  {"class": "lister-item-year text-muted unbold"}).getText()
    except:
        return 'NA'


def getGenre(muted_text):
    try:
        return muted_text.find("span",  {"class":  "genre"}).getText()
    except:
        return 'NA'


def getsynopsys(movie):
    try:
        return movie.find_all("p", {"class":  "text-muted"})[1].getText()
    except:
        return 'NA'


def getImage(image):
    try:
        return image.get('loadlate')
    except:
        return 'NA'


def getImageId(image):
    try:
        return image.get('data-tconst')
    except:
        return 'NA'


def scrape(imdb_url):
    headers = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(imdb_url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    # Movie Name
    # movies = soup.find('div', class_="lister-list").find_all('div')
    # movies = soup.find_all("div", {"class": "lister-item mode-advanced"})
    headers = {"User-Agent": "Mozilla/5.0"}
    page = requests.get('https://www.imdb.com/list/ls024372673/', headers=headers)
    soup = BeautifulSoup(page.content, 'html.parser')
    movies = soup.select('.lister-item')

    for movie in movies:
        print(f"\n\n-----{movie=}")
        header = movie.find_all("h3", {"class": "lister-item-header"})
        muted_text = movie.find_all("p", {"class": "text-muted"})
        if len(muted_text):
            muted_text = muted_text[0]
        # imageDiv = movie.find("div", {"class": "lister-item-image float-left"})
        # image = imageDiv.find("img", "loadlate")

        #  Movie Title
        movie_title = getMovieTitle(header)
        movie_title_arr.append(movie_title)

        #  Movie release year
        year = getReleaseYear(header)
        movie_year_arr.append(year)

        #  Genre  of movie
        genre = getGenre(muted_text)
        movie_genre_arr.append(genre)

        # Movie Synopsys
        synopsis = getsynopsys(movie)
        movie_synopsis_arr.append(synopsis)

        #  Image attributes
        # img_url = getImage(image)
        # image_url_arr.append(img_url)

        # image_id = image.get('data-tconst')
        # image_id_arr.append(image_id)

    # An array to store all the URL that are being queried
    imageArr = []

    # Maximum number of pages one wants to iterate over
    MAX_PAGE = 51

    # Loop to generate all the URLS.
    for i in range(0, MAX_PAGE):
        totalRecords = 0 if i == 0 else (250*i)+1
        print(totalRecords)
        imdb_url = f'https://www.imdb.com/search/title/?release_date=2020-01-02,2021-02-01&user_rating=4.0,10.0&languages=en&count=250&start={totalRecords}&ref_=adv_nxt'
        imageArr.append(imdb_url)

    # Download
    download_stories(imageArr)

    # Attach all the data to the pandas dataframe. You can optionally write it to a CSV file as well
    movieDf = pd.DataFrame({
        "Title": movie_title_arr,
        "Release_Year": movie_year_arr,
        "Genre": movie_genre_arr,
        "Synopsis": movie_synopsis_arr,
        # "image_url": image_url_arr,
        # "image_id": image_id_arr,
    })

    print('--------- Download Complete CSV Formed --------')

    # movieDf.to_csv('file.csv', index=False) : If you want to store the file.
    movieDf.head()


if __name__ == '__main__':
    # url = "http://www.imdb.com/search/title?sort=year,desc&start=1&title_type=feature&year=1930,2024"
    # url = "http://www.imdb.com/search/title?sort=year,desc&start=1&title_type=feature"
    # url = "http://www.imdb.com/search/title?desc&start=1&title_type=feature&year=1950,2024"
    # url = "https://www.imdb.com/search/title/?title_type=tv_episode&num_votes=1000,&sort=user_rating,desc&ref_=adv_prv"
    url = 'https://www.imdb.com/search/title/?title_type=feature&release_date=1930-01-01,2025-01-01&sort=release_date,desc'
    # url = 'https://www.imdb.com/list/ls024372673/'
    scrape(url)
