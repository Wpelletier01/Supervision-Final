import json
import requests
import datetime
import argparse
from typing import Optional, List
from configparser import ConfigParser

# Source du ticket: Other
SOURCE_ID = 6

# type de ticket
INCIDENT = 1
REQUETE = 2

# Niveau d'urgence/Impact
HIGH = 4
VERY_HIGH = 5

class GlpiApi:
    """
    Permet l'interaction avec un serveur GLPI à l'aide des informations de connexion
    prises dans un fichier de config.ini
    """

    def __init__(self, stoken: str, settings: dict, config: ConfigParser):
        """
        Constructeur.

        Args:
            stoken (str): la clé de session
            settings (dict): les paramètres à utiliser (exemple la section development)
            config (ConfigParser): le fichier entier si nous avons besoin de changer le fichier de config
        """
        self.__settings: dict = settings
        self.__stoken: str = stoken
        self.__config: ConfigParser = config

    @classmethod
    def initSession(cls, config: dict):
        """
        Initialise une session dans un serveur Glpi

        Args:
            config (dict): le fichier de config

        Returns:
            GlpiApi: une instance de la classe GlpiApi
        """
        # vérifie le type d'exécution
        if config["GENERAL"]["env"] == "development":
            settings = config["DEVELOPMENT"]
        elif config["GENERAL"]["env"] == "production":
            settings = config["PRODUCTION"]
        else:
            print("La valeur env dans le fichier ne peut être que 'production' ou 'development'")
            exit(1)

        headers = {
            "Content-Type": "application/json",
            "App-Token": settings['api_token'],
            "Authorization": f"user_token {settings['user_token']}"
        }

        # initialise une session
        resp = requests.get(f"{settings['host']}/apirest.php/initSession/", headers=headers, verify=False)

        if resp.status_code != 200:
            print(f"incapable d'initier une connexion au serveur glpi par l'api: {resp.text}")
            exit(1)

        return cls(resp.json()['session_token'], settings, config)

    def killSession(self):
        """
            Ferme une session en cours
        """
        resp = requests.get(f"{self.__settings['host']}/apirest.php/killSession/", headers=self.__gen_headers(),
                            verify=False)

        if resp.status_code != 200:
            print(f"La session n'a pu s'arrêter. Raison: {resp.text}")
            exit(1)

        print("Session arrêtée avec succès")

    def __gen_headers(self) -> dict:
        """
        Génère l'en-tête que toutes les requêtes avec une session initialisée ont besoin

        Returns:
            dict: l'en-tête
        """
        return {
            "Content-Type": "application/json",
            "App-Token": self.__settings["api_token"],
            "Session-Token": self.__stoken
        }

    def query(self, query: str) -> List[dict]:
        """
        Exécute une requête GET au serveur GLPI

        Args:
            query (str): la ou les valeurs qu'on souhaite aller chercher

        Returns:
            List[dict]: le résultat de la requête
        """
        resp = requests.get(f"{self.__settings['host']}/apirest.php/{query}", headers=self.__gen_headers(), verify=False)

        if resp.status_code not in [200, 206]:
            print(f"status: {resp.status_code}")
            print(f"Requête au serveur GLPI ne s'est pas finie correctement: {resp.text}")
            exit(1)

        return resp.json()

    def get_category_name(self) -> str:
        """
        Redonne le nom de la catégorie dans le fichier de config

        Returns:
            str: le nom de la catégorie
        """
        return self.__settings['category_name']

    def get_categories_name(self) -> List[str]:
        """
        Va chercher la liste complète des catégories Itil possibles dans le serveur Glpi
        Returns:
            List[str]: des noms de catégorie
        """
        return list(map(lambda x: x["name"], self.query("itilcategory")))

    def get_exec_id(self) -> int:
        """
        Va chercher l'id de l'exécuteur selon son nom dans le fichier de config
        Returns:
            int: son id
        """
        data = self.query(
            f"/search/User?criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={self.__settings['exec_name']}&forcedisplay[0]=1&forcedisplay[1]=2&forcedisplay[2]=5&forcedisplay[3]=9&forcedisplay[4]=14&forcedisplay[5]=80")
        return data["data"][0]["2"]

    def get_exec_id_from_config(self) -> int:
        """
        Va chercher l'id de l'exécuteur en mémoire dans le fichier de config

        Returns:
            int: l'id de l'exécuteur
        """
        return self.__settings["exec_id"]

    def get_group_id(self) -> int:
        """
        Va chercher l'id du groupe selon le nom du groupe en mémoire dans le fichier de config
        Returns:
            int: l'id du groupe
        """
        data = self.query(
            f"/search/Group?criteria[0][field]=1&criteria[0][searchtype]=contains&criteria[0][value]={self.__settings['group_name']}&forcedisplay[0]=1&forcedisplay[1]=2&forcedisplay[2]=5&forcedisplay[3]=9&forcedisplay[4]=14&forcedisplay[5]=80")
        return data["data"][0]["2"]

    def send_ticket(
            self,
            name: str,
            description: str,
            type_: int,
            urgency: int,
            time_to_own: datetime.datetime,
            time_to_resolve: datetime.datetime):
        """
        Crée un ticket dans le serveur GLPI

        Args:
            name (str): nom du ticket
            description (str): description du ticket
            type_ (int): Le type de ticket (Requête ou Incident)
            urgency (int): Son niveau d'urgence (chiffre de 1 à 5)
            time_to_own (datetime.datetime): Le temps de prise en charge selon l'heure présente
            time_to_resolve (datetime.datetime): Le temps de résolution selon l'heure présente
        """
        time_to_own = (datetime.datetime.now() + time_to_own).strftime("%Y-%m-%d %H:%M:%S")
        time_to_resolve = (datetime.datetime.now() + time_to_resolve).strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "input": [
                {
                    "name": name,
                    "content": description,
                    "type": type_,
                    "urgency": urgency,
                    "itilcategories_id": self.__settings["category_id"],
                    "requesttypes_id": SOURCE_ID,
                    "items_id": {
                        'Computer': [self.__settings["equip_id"]]
                    },
                    "time_to_resolve": str(time_to_own),
                    "time_to_own": str(time_to_resolve),
                    "_groups_id_assign": self.__settings["group_id"],
                    "_users_id_requester": self.__settings["exec_userid"]

                }
            ]
        }

        resp = requests.post(f"{self.__settings['host']}/apirest.php//Ticket", headers=self.__gen_headers(),
                             data=json.dumps(data), verify=False)

        if resp.status_code != 201:
            print(f"Incapable de créer un ticket: {resp.text}")
            exit(1)

        print(f"Création du ticket '{name}' a été un succès")

    def create_category(self):
        """
            Crée une catégorie dans le serveur glpi selon le nom qui est en mémoire dans le fichier de config
        """
        data = {
            "input": [
                {"name": self.__settings['category_name']}
            ]
        }

        resp = requests.post(
            f"{self.__settings['host']}/apirest.php/itilcategory",
            headers=self.__gen_header(),
            data=json.dumps(data),
            verify=False
        )

        if resp.status_code != 201:
            print(f"Incapable de créer une catégorie dans glpi: {resp.text}")
            exit(1)

        print(f"Création de la catégorie '{name}' a été un succès")

    def set_value(self, key: str, value: str):
        """
        Change une valeur dans la section du fichier de config.
        Notez qu'elle doit déjà exister dans le fichier de config.

        Args:
            key (str): le nom de la variable
            value (str): sa valeur
        """

        if key not in self.__settings.keys():
            print(f"clé '{key}' inexistante dans le fichier de config")
            exit(0)

        self.__settings[key] = str(value)

    def update_config(self):
        """
            Met à jour le fichier de config selon les données stockées dans l'instance.
        """
        with open("config.ini", "w") as f:

            self.__config[(self.__config["GENERAL"]["env"]).upper()] = self.__settings

            self.__config.write(f)

            f.close()

    def test_output(self):
        """
            Génère un fichier 'output.txt' avec de l'information recueillie dans le serveur GLPI pour tester.
        """
        with open("output.txt", "w") as f:

            f.write("ordinateur trouvé dans glpi:\n")

            for pc in self.query("Computer"):
                f.write(f"    - Name: {pc['name']} Id: {pc['id']}\n")

            f.write(f"Group name: {self.__settings['group_name']} id: {self.get_group_id()}\n")

            f.write("catégorie trouvée dans glpi:\n")

            for category in self.get_categories_name():
                f.write(f"    - {category}\n")

            f.write(f"\nID de l'exécuteur: {self.get_exec_id()}")

            f.close()

        print("résultat généré dans le fichier output.txt")


if __name__ == "__main__":

    # Désactive les messages d'avertissement non importants du module requests
    requests.packages.urllib3.disable_warnings()

    # Traite les paramètres de ligne de commande
    parser = argparse.ArgumentParser()

    parser.add_argument("-i", "--init", action="store_true")
    parser.add_argument("-t", "--test", action="store_true")
    parser.add_argument("-T", "--title", action="store", dest="title")
    parser.add_argument("-d", "--description", action="store", dest="desc")
    parser.add_argument("-o", "--tto", action="store", dest="tto")
    parser.add_argument("-r", "--ttr", action="store", dest="ttr")
    parser.add_argument("-u", "--urgency", action="store", dest="urgency")
    args = parser.parse_args()

    # Lis le fichier de configuration dans le même dossier
    config = ConfigParser()
    config.read("config.ini")

    # Initialise une session par l'API
    glpi = GlpiApi.initSession(config)

    # Initialisation du fichier de configuration à exécuter en premier pour peupler correctement le fichier de configuration
    if args.init:

        category = glpi.get_category_name()

        # Regarde si une catégorie avec un nom pareil que celui dans le fichier
        # de configuration existe et si non, créé en une.
        if category not in glpi.get_categories_name():

            print(f"La catégorie '{category}' n'existe pas, elle sera créée")

            glpi.create_category()

        # Va chercher l'id de la catégorie créée
        cid = list(filter(lambda n: n['name'] == category, glpi.query("itilcategory")))[0]['id']

        # Va chercher l'id de l'exécuteur
        exec_id = glpi.get_exec_id()

        # Aller chercher l'id d'un ordinateur avec le nom TrueNAS
        pc = list(filter(lambda p: "truenas" in p["name"].lower(), glpi.query("Computer")))

        if len(pc) == 0:
            print("Aucune entrée semble être présente pour un TrueNAS dans GLPI")
            print("La valeur par défaut sera mise, entrez des valeurs manuellement")
            pc = -1
        elif len(pc) > 1:
            print("Impossible de déterminer à 100% l'ordinateur TrueNAS car plusieurs entrées correspondent à notre recherche")
            print("Voici les valeurs trouvées:")
            for t in pc:
                print(f"    - NAME: {t['name']} ID: {t['id']}")
            print("La valeur par défaut sera mise, entrez des valeurs manuellement")
            pc = -1
        else:

            print(f"L'ordinateur {pc[0]['name']} avec ID: {pc[0]['id']} sera utilisé comme la valeur de l'équipement")
            pc = pc[0]['id']

        # Met à jour les valeurs dans le fichier de configuration
        glpi.set_value("category_id", cid)
        glpi.set_value("equip_id", pc)
        glpi.set_value("exec_userid", exec_id)
        glpi.set_value("group_id", glpi.get_group_id())

        glpi.update_config()

        print("Fichier de configuration généré")
    # Si on veut juste tester
    elif args.test:
        
        glpi.test_output()

    # L'envoi d'un ticket
    else:

        glpi.send_ticket(
            args.title,
            args.desc,
            INCIDENT,
            args.urgency,
            datetime.timedelta(days=365, minutes=int(args.tto)),
            datetime.timedelta(days=365, minutes=int(args.ttr))
        )

    glpi.killSession()